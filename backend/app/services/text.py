"""Cleaning extracted text and splitting it into overlapping chunks.

Chunk sizes are counted in approximate tokens: words and punctuation marks, which runs a little
under the embedding model's WordPiece count. 400 of them is roughly 450 to 500 model tokens,
inside bge-small's 512-token window, so nothing is silently cut off when a chunk is embedded.
"""

import re
from collections import Counter
from dataclasses import dataclass

from app.sources import PageText

_TOKEN = re.compile(r"\w+|[^\w\s]")
_SENTENCE_END = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9])")
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_PAGE_NUMBER = re.compile(r"^(page\s*)?\d{1,4}(\s*(of|/)\s*\d{1,4})?$", re.IGNORECASE)


def count_tokens(text: str) -> int:
    return len(_TOKEN.findall(text))


# --- cleaning -------------------------------------------------------------------------------


def clean_pages(pages: list[PageText]) -> list[PageText]:
    """Drop running headers, footers and page numbers; repair line wrapping; tidy whitespace."""
    repeated = _repeated_paragraphs(pages)
    cleaned = []
    for page in pages:
        paragraphs = []
        for para in _paragraphs(page.text):
            if _norm(para) in repeated or _PAGE_NUMBER.match(para.strip()):
                continue
            para = _HYPHEN_BREAK.sub(r"\1\2", para)
            para = re.sub(r"\s+", " ", para).strip()
            if para:
                paragraphs.append(para)
        cleaned.append(PageText(page=page.page, text="\n\n".join(paragraphs)))
    return cleaned


def _paragraphs(text: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def _norm(paragraph: str) -> str:
    # Page numbers inside a header ("Chapter 3 · 17") change per page, so mask digits.
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", paragraph).strip().lower())


def _repeated_paragraphs(pages: list[PageText]) -> set[str]:
    """Short paragraphs at the top or bottom of most pages are headers or footers."""
    if len(pages) < 3:
        return set()
    seen: Counter[str] = Counter()
    for page in pages:
        paras = _paragraphs(page.text)
        edges = paras[:2] + paras[-2:]
        seen.update({_norm(p) for p in edges if len(p) < 200})
    threshold = max(3, int(len(pages) * 0.5))
    return {para for para, n in seen.items() if n >= threshold}


# --- chunking -------------------------------------------------------------------------------


@dataclass(frozen=True)
class ChunkText:
    text: str
    page: int | None


@dataclass(frozen=True)
class _Unit:
    text: str
    page: int | None
    tokens: int
    starts_paragraph: bool


def chunk_pages(pages: list[PageText], size: int = 400, overlap: int = 60) -> list[ChunkText]:
    """Pack sentences into chunks of at most `size` tokens, keeping paragraph breaks. Each chunk
    starts with up to `overlap` tokens from the end of the one before, so a fact split across a
    boundary is still whole in one of them. A chunk records the page its first new sentence is
    on.
    """
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    units = list(_units(pages, size))
    chunks: list[ChunkText] = []
    current: list[_Unit] = []
    tokens = 0
    fresh = 0  # units in `current` that aren't overlap carried from the previous chunk

    for unit in units:
        if current and fresh and tokens + unit.tokens > size:
            chunks.append(_join(current, current[-fresh]))
            current = _tail(current, overlap)
            tokens = sum(u.tokens for u in current)
            fresh = 0
        current.append(unit)
        tokens += unit.tokens
        fresh += 1
    if fresh:
        chunks.append(_join(current, current[-fresh]))
    return chunks


def _units(pages: list[PageText], size: int):
    for page in pages:
        for para in _paragraphs(page.text):
            first = True
            for piece in _sentences(para.strip(), size):
                yield _Unit(piece, page.page, count_tokens(piece), first)
                first = False


def _sentences(paragraph: str, size: int):
    """Split by sentence; a single sentence still over `size` is cut into word windows.

    Sentences are the packing unit so the overlap can be close to its target size.
    """
    for sentence in _SENTENCE_END.split(paragraph):
        if count_tokens(sentence) <= size:
            yield sentence
            continue
        words = sentence.split()
        window: list[str] = []
        for word in words:
            if window and count_tokens(" ".join([*window, word])) > size:
                yield " ".join(window)
                window = []
            window.append(word)
        if window:
            yield " ".join(window)


def _tail(units: list[_Unit], overlap: int) -> list[_Unit]:
    tail: list[_Unit] = []
    tokens = 0
    for unit in reversed(units):
        if tokens + unit.tokens > overlap:
            break
        tail.insert(0, unit)
        tokens += unit.tokens
    return tail


def _join(units: list[_Unit], first_fresh: _Unit) -> ChunkText:
    parts = []
    for i, unit in enumerate(units):
        if i:
            parts.append("\n\n" if unit.starts_paragraph else " ")
        parts.append(unit.text)
    return ChunkText(text="".join(parts), page=first_fresh.page)
