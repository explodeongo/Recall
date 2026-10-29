"""Answers from the web, for questions your library doesn't cover.

Grounded the same way as library answers: search the web, read the top pages, keep the
passages closest to the question, and let the model answer only from those, citing them. The
model never answers from its own memory, which is where made-up answers come from.

Search providers sit behind `WebSearcher` and are tried in order until one returns results:
Tavily when TAVILY_API_KEY is set (fast and reliable, made for this; free plan of 1,000
searches a month, and it returns page text so pages needn't be fetched), then the free
engines DuckDuckGo, Bing and Google (no key, but rate-limited under heavy use), then
Wikipedia's own search API. Results are cached for a few minutes.
"""

import logging
import math
import re
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import httpx

from app.models import Item, SourceType
from app.services.search import Passage
from app.services.text import chunk_pages, clean_pages

log = logging.getLogger("recall.web")

PAGES_TO_READ = 3
PASSAGES = 5
PER_PAGE = 2  # passages from any one page, so answers draw on more than one source
FETCH_TIMEOUT_S = 4.0


@dataclass(frozen=True)
class WebResult:
    title: str
    url: str
    snippet: str
    # The page's text when the search provider already read it (Tavily); saves a fetch.
    content: str = ""


class WebSearcher(Protocol):
    def search(self, query: str, n: int) -> list[WebResult]: ...


class TavilySearcher:
    def __init__(self, api_key: str):
        self._client = httpx.Client(timeout=10)
        self._key = api_key

    def search(self, query: str, n: int) -> list[WebResult]:
        resp = self._client.post(
            "https://api.tavily.com/search",
            json={
                "query": query,
                "max_results": n,
                "search_depth": "basic",
                "include_raw_content": "text",
            },
            headers={"Authorization": f"Bearer {self._key}"},
        )
        resp.raise_for_status()
        return [
            WebResult(
                r.get("title", ""),
                r.get("url", ""),
                r.get("content", ""),
                (r.get("raw_content") or "")[:60_000],
            )
            for r in resp.json().get("results", [])
            if r.get("url", "").startswith(("http://", "https://"))
        ]


class FreeEngineSearcher:
    """DuckDuckGo, then Bing, then Google, through the ddgs library. No key needed."""

    BACKENDS = ("duckduckgo", "bing", "google")

    def search(self, query: str, n: int) -> list[WebResult]:
        from ddgs import DDGS

        for backend in self.BACKENDS:
            try:
                rows = DDGS(timeout=6).text(query, max_results=n, backend=backend) or []
            except Exception as exc:  # "no results" and rate limits come back as exceptions
                log.info("%s search failed: %s", backend, exc)
                continue
            results = [
                WebResult(r.get("title", "").strip(), r.get("href", ""), r.get("body", "").strip())
                for r in rows
                if r.get("href", "").startswith(("http://", "https://"))
            ]
            if results:
                return unglue(results)
        return []


def _cut_at_others(text: str, others: list[str]) -> str:
    """`text` up to where any of `others` begins inside it."""
    cut = len(text)
    for other in others:
        if len(other) >= 12:
            at = text.find(other[:40], 1)
            if 0 < at < cut:
                cut = at
    return text[:cut].strip()


def unglue(results: list[WebResult]) -> list[WebResult]:
    """Some engines' pages come back with each result's title and snippet running on into the
    next ones' ("Name - LinkedInName (@name) • Instagram…"); cut each where another's starts."""
    titles = [r.title for r in results]
    bodies = [r.snippet for r in results]
    return [
        WebResult(
            _cut_at_others(r.title, titles[:i] + titles[i + 1 :]) or r.title,
            r.url,
            _cut_at_others(r.snippet, bodies[:i] + bodies[i + 1 :]) or r.snippet,
            r.content,
        )
        for i, r in enumerate(results)
    ]


class WikipediaSearcher:
    """Wikipedia's own search API: dependable for facts, people, places and concepts."""

    def search(self, query: str, n: int) -> list[WebResult]:
        from app.sources.url import user_agent

        resp = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": min(n, 3),
                "format": "json",
                "formatversion": 2,
            },
            headers={"User-Agent": user_agent()},
            timeout=6,
        )
        resp.raise_for_status()
        return [
            WebResult(
                r["title"],
                "https://en.wikipedia.org/wiki/" + r["title"].replace(" ", "_"),
                re.sub(r"<[^>]+>", "", r.get("snippet", "")),
            )
            for r in resp.json().get("query", {}).get("search", [])
        ]


class ChainSearcher:
    """Tries each searcher in turn and caches what it finds for CACHE_SECONDS."""

    CACHE_SECONDS = 600

    def __init__(self, searchers: list[WebSearcher]):
        self.searchers = searchers
        self._cache: dict[tuple[str, int], tuple[float, list[WebResult]]] = {}
        self._lock = threading.Lock()

    def search(self, query: str, n: int) -> list[WebResult]:
        key = (" ".join(query.lower().split()), n)
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.monotonic() - hit[0] < self.CACHE_SECONDS:
                return hit[1]
        results: list[WebResult] = []
        for searcher in self.searchers:
            try:
                results = searcher.search(query, n)
            except Exception as exc:
                log.warning("%s failed: %s", type(searcher).__name__, exc)
                continue
            if results:
                break
        if results:
            with self._lock:
                self._cache[key] = (time.monotonic(), results)
        return results


@lru_cache
def get_web_searcher() -> WebSearcher:
    from app.config import get_settings

    key = get_settings().tavily_api_key
    chain: list[WebSearcher] = [TavilySearcher(key)] if key else []
    return ChainSearcher([*chain, FreeEngineSearcher(), WikipediaSearcher()])


_pages: dict[str, tuple[float, str]] = {}
_pages_lock = threading.Lock()
PAGE_CACHE_SECONDS = 600


def _read_page(result: WebResult) -> str:
    """The page's main text, read the same way saved links are (private addresses blocked).
    Pages are cached for a few minutes, so follow-up questions don't fetch them again."""
    with _pages_lock:
        hit = _pages.get(result.url)
        if hit and time.monotonic() - hit[0] < PAGE_CACHE_SECONDS:
            return hit[1]
    text = _fetch_page(result)
    with _pages_lock:
        _pages[result.url] = (time.monotonic(), text)
    return text


def _fetch_page(result: WebResult) -> str:
    from app.sources.url import UrlSource, user_agent

    client = httpx.Client(timeout=FETCH_TIMEOUT_S, headers={"User-Agent": user_agent()})
    try:
        doc = UrlSource(client=client).extract(
            Item(title=result.title, source_type=SourceType.url, source=result.url)
        )
        return "\n\n".join(p.text for p in clean_pages(doc.pages) if p.text)
    except Exception as exc:  # unreadable pages just fall back to the search snippet
        log.info("couldn't read %s: %s", result.url, exc)
        return ""
    finally:
        client.close()


def web_passages(
    query: str,
    searcher: WebSearcher | None = None,
    read_page=None,
) -> list[Passage]:
    """The web passages closest to `query`, best first."""
    read_page = read_page or _read_page
    results = (searcher or get_web_searcher()).search(query, PAGES_TO_READ + 2)
    if not results:
        return []
    results = results[:PAGES_TO_READ]
    to_read = [r for r in results if not r.content]  # Tavily already read its pages
    texts: dict[str, str] = {}
    if to_read:
        with ThreadPoolExecutor(max_workers=PAGES_TO_READ) as pool:
            futures = {pool.submit(read_page, r): r for r in to_read}
            texts = {futures[f].url: f.result() for f in as_completed(futures)}

    # (page, passage, how far into the page it is)
    candidates: list[tuple[WebResult, str, int]] = []
    for result in results:
        text = result.content or texts.get(result.url) or ""
        if text:
            from app.sources import PageText

            chunks = chunk_pages([PageText(None, text)], size=220, overlap=30)[:25]
            candidates += [(result, c.text, n) for n, c in enumerate(chunks)]
        elif result.snippet:
            candidates.append((result, result.snippet, 0))
    if not candidates:
        return []

    scored = sorted(
        zip(candidates, _keyword_scores(query, candidates), strict=True),
        key=lambda pair: -pair[1],
    )
    picked: list[Passage] = []
    per_page: dict[str, int] = {}
    for (result, text, _), score in scored:
        if per_page.get(result.url, 0) >= PER_PAGE:
            continue
        per_page[result.url] = per_page.get(result.url, 0) + 1
        picked.append(
            Passage(
                chunk_id=None,
                item_id=None,
                title=result.title or result.url,
                source_type=SourceType.url,
                source=result.url,
                page=None,
                text=text,
                score=float(score),
                kind="web",
            )
        )
        if len(picked) == PASSAGES:
            break
    return picked


# Words too common to tell one passage from another.
_COMMON_WORDS = (
    "a an and are as at be by can did do does for from how i in is it of on or that the this "
    "to was what when where which who why with you your"
)
_COMMON = frozenset(_COMMON_WORDS.split())


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"\w+", text.lower()) if w not in _COMMON]


def _keyword_scores(query: str, candidates: list[tuple[WebResult, str, int]]) -> list[float]:
    """BM25 over the candidates, leaning towards each page's opening passages, where pages say
    what they're about. Embedding the candidates instead (up to 75 a question) took about 2 s
    of CPU: half a minute on a host with a tenth of a CPU. On 20 real questions an AI judge
    found these picks answered them as well (37 of 40 points, against 38 for embeddings)."""
    k1, b = 1.2, 0.75
    docs = [_words(text) for _, text, _ in candidates]
    average = sum(map(len, docs)) / len(docs) or 1
    seen_in = Counter(w for doc in docs for w in set(doc))
    terms = set(_words(query))
    scores = []
    for doc, (_, _, position) in zip(docs, candidates, strict=True):
        counts = Counter(doc)
        score = 0.0
        for term in terms & counts.keys():
            rarity = math.log(1 + (len(docs) - seen_in[term] + 0.5) / (seen_in[term] + 0.5))
            tf = counts[term]
            score += rarity * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(doc) / average))
        scores.append(score / (1 + 0.15 * position))
    return scores
