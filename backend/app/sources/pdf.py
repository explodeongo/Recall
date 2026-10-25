from pathlib import Path

import pymupdf

from app.errors import PermanentError
from app.models import Item
from app.sources import ExtractedDoc, PageText

# Metadata titles that word processors fill in for you and that mean nothing to a reader.
_JUNK_TITLE_PREFIXES = ("microsoft word", "untitled", "document", "slide 1", "powerpoint")


class PdfSource:
    """Extracts text page by page with PyMuPDF, keeping page numbers for citations."""

    def extract(self, item: Item) -> ExtractedDoc:
        path = Path(item.source)
        if not path.exists():
            raise PermanentError("The uploaded file is missing from storage")
        return extract_pdf_bytes(path.read_bytes())


def extract_pdf_bytes(data: bytes) -> ExtractedDoc:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise PermanentError("This file couldn't be opened as a PDF") from exc

    with doc:
        if doc.needs_pass:
            raise PermanentError("This PDF is password-protected")
        pages = [PageText(page=i + 1, text=_page_text(page)) for i, page in enumerate(doc)]
        title = _clean_title((doc.metadata or {}).get("title"))
    return ExtractedDoc(title=title, pages=pages)


def _page_text(page: pymupdf.Page) -> str:
    # Each text block is roughly a paragraph. Joining its lines with spaces undoes the PDF's
    # line wrapping; the cleaning step then repairs words hyphenated across lines.
    paragraphs = []
    for block in page.get_text("blocks", sort=True):
        if block[6] != 0:  # 0 = text block, 1 = image
            continue
        text = "\n".join(line.strip() for line in block[4].splitlines() if line.strip())
        if text:
            paragraphs.append(text)
    return "\n\n".join(paragraphs)


def _clean_title(title: str | None) -> str | None:
    title = (title or "").strip()
    if len(title) < 4 or title.lower().startswith(_JUNK_TITLE_PREFIXES):
        return None
    if title.lower().endswith((".doc", ".docx", ".pdf", ".tex", ".dvi")):
        return None
    return title[:500]
