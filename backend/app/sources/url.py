import ipaddress
import re
import socket
from collections.abc import Callable
from urllib.parse import urljoin, urlsplit

import httpx
import trafilatura

from app.config import get_settings
from app.errors import PermanentError
from app.models import Item
from app.sources import ExtractedDoc, PageText
from app.sources.pdf import extract_pdf_bytes


def user_agent() -> str:
    """An honest user agent. Sites such as Wikipedia block clients that pretend to be a browser
    and ask bots to give a contact (FETCH_CONTACT: a repo URL or email)."""
    contact = get_settings().fetch_contact
    return f"Recall/0.2 (personal knowledge base{f'; +{contact}' if contact else ''})"


MAX_REDIRECTS = 5

Resolver = Callable[[str], list[str]]


def _resolve(host: str) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


# Wikipedia-style "[edit]" links and footnote markers like "[12]"; left in, the markers look
# like Recall's own [n] citations to the model.
_WEB_MARKERS = re.compile(r"\[(?:edit|\d{1,3}|citation needed|note \d+)\]", re.IGNORECASE)
_TABLE_RULE = re.compile(r"^[\s|:\-+=]*$")
_EMPTY_CELLS = re.compile(r"(?:\|\s*){2,}")


def _tidy(line: str) -> str:
    """Clean one line of extracted article text; tables come through as `a | b | c` rows."""
    line = _WEB_MARKERS.sub("", line).strip()
    if _TABLE_RULE.match(line):
        return ""
    line = _EMPTY_CELLS.sub("| ", line).strip(" |")
    return line if any(ch.isalnum() for ch in line) else ""


def _strip_site_name(title: str, site: str | None, host: str | None = None) -> str | None:
    """'B-tree - Wikipedia' -> 'B-tree', when the suffix is the site's name or domain."""
    names = {site.strip().lower()} if site else set()
    if host:
        labels = host.lower().removeprefix("www.").split(".")
        names |= {".".join(labels[i:]) for i in range(len(labels) - 1)}
        names |= {label for label in labels[:-1] if len(label) > 3}
    for sep in (" - ", " | ", " – ", " — ", " · "):
        head, found, tail = title.rpartition(sep)
        if found and head.strip() and tail.strip().lower() in names:
            return head.strip()
    return title or None


class UrlSource:
    """Fetches a web page and pulls out the article text with trafilatura.

    A link that serves a PDF (an arXiv paper, say) is read as a PDF, page numbers included.
    """

    def __init__(self, client: httpx.Client | None = None, resolve: Resolver = _resolve):
        settings = get_settings()
        self._client = client or httpx.Client(
            timeout=settings.fetch_timeout_s, headers={"User-Agent": user_agent()}
        )
        self._resolve = resolve
        self._max_bytes = settings.max_fetch_mb * 1024 * 1024
        self._allow_private = settings.allow_private_urls

    def extract(self, item: Item) -> ExtractedDoc:
        final_url, content_type, body = self._fetch(item.source)
        if "application/pdf" in content_type or body.startswith(b"%PDF-"):
            return extract_pdf_bytes(body)

        doc = trafilatura.bare_extraction(
            body,
            url=final_url,
            with_metadata=True,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
        )
        text = (getattr(doc, "text", None) or "").strip() if doc is not None else ""
        if not text:
            raise PermanentError(
                "No article text found on that page. It may need a login, block automated "
                "readers, or be mostly images or video."
            )
        # trafilatura puts one paragraph per line; the rest of the pipeline wants blank lines.
        paragraphs = [p for p in (_tidy(line) for line in text.splitlines()) if p]
        title = _strip_site_name(
            (getattr(doc, "title", None) or "").strip(),
            getattr(doc, "sitename", None),
            urlsplit(final_url).hostname,
        )
        return ExtractedDoc(title=title, pages=[PageText(page=None, text="\n\n".join(paragraphs))])

    def _fetch(self, url: str) -> tuple[str, str, bytes]:
        """GET with redirects followed by hand, so every hop gets the private-address check."""
        for _ in range(MAX_REDIRECTS + 1):
            self._check_public(url)
            try:
                with self._client.stream("GET", url, follow_redirects=False) as resp:
                    if resp.is_redirect and "location" in resp.headers:
                        url = urljoin(url, resp.headers["location"])
                        continue
                    if resp.status_code in (401, 403):
                        raise PermanentError(
                            f"The site refused access ({resp.status_code}). "
                            "It may need a login or block automated readers."
                        )
                    if resp.status_code == 404:
                        raise PermanentError("The page wasn't found (404)")
                    if resp.status_code >= 500 or resp.status_code == 429:
                        # Worth retrying later: raise something the worker treats as transient.
                        raise httpx.HTTPStatusError(
                            f"Site returned {resp.status_code}", request=resp.request, response=resp
                        )
                    if resp.status_code >= 400:
                        raise PermanentError(f"The site returned an error ({resp.status_code})")
                    return url, resp.headers.get("content-type", ""), self._read_capped(resp)
            except httpx.TransportError as exc:
                if isinstance(exc, httpx.UnsupportedProtocol):
                    raise PermanentError("Only http and https links are supported") from exc
                raise
        raise PermanentError("The link redirected too many times")

    def _read_capped(self, resp: httpx.Response) -> bytes:
        body = bytearray()
        for chunk in resp.iter_bytes():
            body.extend(chunk)
            if len(body) > self._max_bytes:
                raise PermanentError(f"The page is larger than {self._max_bytes // 2**20} MB")
        return bytes(body)

    def _check_public(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise PermanentError("Only http and https links are supported")
        if self._allow_private:
            return
        try:
            addresses = self._resolve(parts.hostname)
        except OSError as exc:
            raise PermanentError(f"Couldn't find the site {parts.hostname}") from exc
        for addr in addresses:
            ip = ipaddress.ip_address(addr.split("%", 1)[0])
            if not ip.is_global:
                raise PermanentError("Links to private or local network addresses aren't allowed")
