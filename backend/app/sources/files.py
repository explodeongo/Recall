"""Uploaded documents other than PDFs: Word (.docx), Markdown and plain text."""

import re
from pathlib import Path

from app.errors import PermanentError
from app.models import Item
from app.sources import ExtractedDoc, PageText

EXTENSIONS = {".docx", ".md", ".markdown", ".txt"}
_LIST_ITEM = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+")


class FileSource:
    def extract(self, item: Item) -> ExtractedDoc:
        path = Path(item.source)
        if not path.exists():
            raise PermanentError("The uploaded file is missing from storage")
        suffix = path.suffix.lower()
        if suffix == ".docx":
            return _docx(path)
        text = path.read_bytes().decode("utf-8", errors="replace")
        if suffix in (".md", ".markdown"):
            return _markdown(text)
        return ExtractedDoc(
            title=None, pages=[PageText(None, _join(paragraphs_from_plain_text(text)))]
        )


def paragraphs_from_plain_text(text: str) -> list[str]:
    """Blank lines separate paragraphs; inside one, wrapped lines are joined, but list items
    and short lines that look like headings keep their own line."""
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        if any(_LIST_ITEM.match(line) for line in lines):
            paragraphs.extend(lines)
        else:
            paragraphs.append(" ".join(lines))
    return paragraphs


def _join(paragraphs: list[str]) -> str:
    return "\n\n".join(paragraphs)


def _markdown(text: str) -> ExtractedDoc:
    title = None
    heading = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if heading:
        title = heading.group(1).strip()
    text = re.sub(r"```[^\n]*\n", "", text)  # fences go, code stays
    text = re.sub(r"^#{1,6}\s+(.+)$", r"\n\1\n", text, flags=re.MULTILINE)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)  # images: keep the alt text
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # links: keep the label
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)
    text = re.sub(r"(?<![\w*])([*_])(?!\s)(.+?)(?<!\s)\1(?![\w*])", r"\2", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE)
    return ExtractedDoc(
        title=title, pages=[PageText(None, _join(paragraphs_from_plain_text(text)))]
    )


def _docx(path: Path) -> ExtractedDoc:
    import docx

    try:
        document = docx.Document(str(path))
    except Exception as exc:  # python-docx raises several kinds for a damaged file
        raise PermanentError("This file couldn't be opened as a Word document") from exc
    paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                paragraphs.append(" | ".join(dict.fromkeys(cells)))
    title = (document.core_properties.title or "").strip() or None
    return ExtractedDoc(title=title, pages=[PageText(None, _join(paragraphs))])
