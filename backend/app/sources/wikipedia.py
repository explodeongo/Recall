"""Wikipedia's printable PDF of an article.

Wikipedia renders every article as a PDF. Recall keeps it when a Wikipedia link is saved, so
the Read tab can show the article as pages, like an uploaded PDF. Other sites have no such
version. The text Recall searches and cites still comes from the page itself.
"""

import logging
import re

import httpx

from app.config import get_settings

log = logging.getLogger("recall.wikipedia")

# An article on any language's Wikipedia, desktop or mobile.
ARTICLE = re.compile(r"^https?://([a-z][a-z-]*)\.(?:m\.)?wikipedia\.org/wiki/([^?#]+)")


def pdf_url(link: str) -> str | None:
    """Where Wikipedia serves `link`'s article as a PDF; None for anything else."""
    match = ARTICLE.match(link)
    if not match:
        return None
    language, title = match.groups()
    # A slash inside a title ("A/B testing") is part of the name, not the path.
    return f"https://{language}.wikipedia.org/api/rest_v1/page/pdf/{title.replace('/', '%2F')}"


def fetch_pdf(link: str) -> bytes | None:
    """The article's PDF, or None when `link` isn't a Wikipedia article or it can't be had.
    Rendering a long article takes Wikipedia a few seconds."""
    url = pdf_url(link)
    if url is None:
        return None
    from app.sources.url import user_agent

    settings = get_settings()
    try:
        resp = httpx.get(
            url, timeout=30, follow_redirects=True, headers={"User-Agent": user_agent()}
        )
    except httpx.HTTPError as exc:
        log.info("couldn't fetch the PDF of %s: %s", link, exc)
        return None
    data = resp.content
    if resp.status_code != 200 or not data.startswith(b"%PDF-"):
        log.info("no PDF for %s (%s)", link, resp.status_code)
        return None
    return data if len(data) <= settings.max_fetch_mb * 1024 * 1024 else None
