"""Linked ideas: while reading one item, the names of things that other saved items are about.

Each item contributes the terms it can be found by: its title (when short enough to be a
name, like "Okapi BM25" or "Forgetting curve") and the concepts picked out when it was read
(enrich.py: methods, theories, chemicals, people). Those terms are found in the text being
read with plain matching, so links appear instantly and no model is involved. Each one
points at the items it came from, with the passage there that mentions it.
"""

import re
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Chunk, Item, ItemStatus

PER_TERM = 2  # occurrences marked per term
MAX_LINKS = 80
MAX_TARGETS = 4
# Words too common to be worth a link, even when an item is named or tagged with them.
GENERIC = {
    "history", "overview", "introduction", "example", "examples", "summary", "notes", "note",
    "data", "model", "models", "method", "methods", "system", "systems", "study", "research",
    "theory", "people", "time", "memory", "learning", "design", "product", "search", "index",
    "attention", "information", "knowledge", "network", "networks", "language", "test",
}  # fmt: skip


@dataclass
class Target:
    item_id: int
    title: str
    cover_image_id: int | None
    snippet: str | None = None
    chunk_id: int | None = None
    start_char: int | None = None
    end_char: int | None = None


@dataclass
class Link:
    term: str
    start: int
    end: int
    targets: list[Target] = field(default_factory=list)


def title_terms(title: str) -> list[str]:
    """How an item's title is likely to be written in other texts: "Transformer (deep
    learning)" → "Transformer"; long titles ("Let's build GPT: from scratch…") are not names."""
    base = re.sub(r"\s*\([^)]*\)", "", title).strip()
    base = re.split(r"\s+[|–—-]\s+", base)[0].strip()
    return [base] if 1 <= len(base.split()) <= 4 else []


DASHES = "-‐‑‒–—"


def _key(term: str) -> str:
    """Terms compare without case, with any dash as a hyphen and spaces collapsed: "TF-IDF",
    "tf–idf" and "tf - idf" are one term."""
    return re.sub(r"\s+", " ", re.sub(f"[{DASHES}]", "-", term.lower())).strip()


def _pattern(key: str) -> str:
    """A key as a regex that matches any of its spellings."""
    return "".join(
        f"[{DASHES}]" if ch == "-" else r"\s+" if ch == " " else re.escape(ch) for ch in key
    )


def _usable(term: str) -> bool:
    return len(term) >= 3 and term.lower() not in GENERIC


def links_for(session: Session, item: Item) -> list[Link]:
    if not item.content:
        return []
    text = "\n\n".join(p["text"] for p in item.content)
    others = session.execute(
        select(Item.id, Item.title, Item.details, Item.cover_image_id).where(
            Item.user_id == item.user_id,
            Item.id != item.id,
            Item.status == ItemStatus.ready,
            Item.archived.is_(False),
        )
    ).all()
    own = {_key(t) for t in title_terms(item.title)}
    by_term: dict[str, dict[int, Target]] = {}
    spelling: dict[str, str] = {}
    for row in others:
        terms = title_terms(row.title) + list((row.details or {}).get("concepts") or [])
        for term in terms:
            key = _key(term)
            if not _usable(term) or key in own:
                continue
            spelling.setdefault(key, term)
            by_term.setdefault(key, {})[row.id] = Target(row.id, row.title, row.cover_image_id)
    if not by_term:
        return []

    # Longest first, so "Okapi BM25" wins over "BM25" where both match. A term may start a
    # hyphenated compound ("TF-IDF-like") but not sit inside one.
    keys = sorted(by_term, key=len, reverse=True)
    pattern = re.compile(
        r"(?<![\w-])(" + "|".join(_pattern(k) for k in keys) + r")(?!\w)", re.IGNORECASE
    )
    links: list[Link] = []
    counts: dict[str, int] = {}
    for match in pattern.finditer(text):
        key = _key(match.group(1))
        # Short all-capital terms (BM25, RNN) must match their case: "rnn" in prose isn't one.
        canonical = spelling[key]
        if len(canonical) <= 5 and canonical.isupper() and match.group(1) != canonical:
            continue
        if counts.get(key, 0) >= PER_TERM:
            continue
        counts[key] = counts.get(key, 0) + 1
        targets = list(by_term[key].values())[:MAX_TARGETS]
        links.append(Link(match.group(1), match.start(1), match.end(1), targets))
        if len(links) == MAX_LINKS:
            break
    _add_passages(session, links)
    return links


def _add_passages(session: Session, links: list[Link]) -> None:
    """For each target, the passage in it that mentions the term (once per term and item)."""
    found: dict[tuple[str, int], Chunk | None] = {}
    for link in links:
        for target in link.targets:
            key = (_key(link.term), target.item_id)
            if key not in found:
                found[key] = session.scalars(
                    select(Chunk)
                    .where(
                        Chunk.item_id == target.item_id,
                        Chunk.kind == "text",
                        func.lower(Chunk.chunk_text).contains(link.term.lower()),
                    )
                    .order_by(Chunk.chunk_index)
                    .limit(1)
                ).first()
            chunk = found[key]
            if chunk is None:
                continue
            target.chunk_id, target.start_char, target.end_char = (
                chunk.id,
                chunk.start_char,
                chunk.end_char,
            )
            target.snippet = _window(chunk.chunk_text, link.term)


def _window(text: str, term: str, around: int = 140) -> str:
    """The text around the first mention of `term`, trimmed to whole words."""
    flat = " ".join(text.split())
    at = flat.lower().find(term.lower())
    if at == -1:
        return flat[: around * 2] + ("…" if len(flat) > around * 2 else "")
    start, end = max(0, at - around), min(len(flat), at + len(term) + around)
    if start > 0:
        start = flat.find(" ", start) + 1
    if end < len(flat):
        end = flat.rfind(" ", 0, end)
    return ("…" if start > 0 else "") + flat[start:end] + ("…" if end < len(flat) else "")
