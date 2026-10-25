"""YouTube videos, read from their captions.

The transcript is grouped into paragraphs of about a minute, each starting with its time
("[12:34]"), so a cited passage can open the video at the right moment.
"""

import re
from collections.abc import Callable
from urllib.parse import parse_qs, urlsplit

import httpx

from app.config import get_settings
from app.errors import PermanentError
from app.models import Item
from app.sources import ExtractedDoc, PageText
from app.sources.url import user_agent

PARAGRAPH_SECONDS = 60
_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def video_id(url: str) -> str | None:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    if host == "youtu.be":
        candidate = parts.path.strip("/").split("/")[0]
    elif host in ("youtube.com", "music.youtube.com"):
        if parts.path == "/watch":
            candidate = parse_qs(parts.query).get("v", [""])[0]
        else:
            match = re.match(r"^/(?:shorts|embed|live)/([^/?#]+)", parts.path)
            candidate = match.group(1) if match else ""
    else:
        return None
    return candidate if _ID.match(candidate) else None


def timestamp(seconds: float) -> str:
    seconds = int(seconds)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


Fetcher = Callable[[str], list[tuple[float, str]]]


def _fetch_transcript(vid: str) -> list[tuple[float, str]]:
    from youtube_transcript_api import (
        NoTranscriptFound,
        TranscriptsDisabled,
        VideoUnavailable,
        YouTubeTranscriptApi,
    )

    api = YouTubeTranscriptApi()
    try:
        try:
            fetched = api.fetch(vid, languages=("en", "en-US", "en-GB"))
        except NoTranscriptFound:
            # No English captions: take whatever language the video has.
            fetched = next(iter(api.list(vid))).fetch()
    except (TranscriptsDisabled, NoTranscriptFound, StopIteration) as exc:
        raise PermanentError("This video has no captions, so there's nothing to read.") from exc
    except VideoUnavailable as exc:
        raise PermanentError("This video is unavailable or private.") from exc
    return [(s.start, s.text) for s in fetched.snippets]


class YoutubeSource:
    def __init__(self, fetch: Fetcher = _fetch_transcript, client: httpx.Client | None = None):
        self._fetch = fetch
        self._client = client or httpx.Client(
            timeout=get_settings().fetch_timeout_s, headers={"User-Agent": user_agent()}
        )

    def extract(self, item: Item) -> ExtractedDoc:
        vid = video_id(item.source)
        if vid is None:
            raise PermanentError("That doesn't look like a YouTube video link")
        snippets = self._fetch(vid)
        paragraphs: list[str] = []
        current: list[str] = []
        started = None
        for start, text in snippets:
            text = " ".join(text.replace("\n", " ").split())
            if not text or text.startswith("[") and text.endswith("]"):  # [Music], [Applause]
                continue
            if started is None:
                started = start
            current.append(text)
            if start - started >= PARAGRAPH_SECONDS:
                paragraphs.append(f"[{timestamp(started)}] {' '.join(current)}")
                current, started = [], None
        if current:
            paragraphs.append(f"[{timestamp(started or 0)}] {' '.join(current)}")
        if not paragraphs:
            raise PermanentError("This video's captions are empty.")
        return ExtractedDoc(
            title=self._title(item.source), pages=[PageText(None, "\n\n".join(paragraphs))]
        )

    def _title(self, url: str) -> str | None:
        try:
            resp = self._client.get(
                "https://www.youtube.com/oembed", params={"url": url, "format": "json"}
            )
            return resp.json().get("title") if resp.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            return None
