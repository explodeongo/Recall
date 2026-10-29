from typing import TYPE_CHECKING

from app.errors import PermanentError
from app.models import Item
from app.services import files
from app.services.images import ExtractedImage, render_pdf_page
from app.sources import ExtractedDoc, PageText

if TYPE_CHECKING:
    import pymupdf

# Metadata titles that word processors fill in for you and that mean nothing to a reader.
_JUNK_TITLE_PREFIXES = ("microsoft word", "untitled", "document", "slide 1", "powerpoint")


class PdfSource:
    """Extracts text page by page with PyMuPDF, keeping page numbers for citations."""

    def extract(self, item: Item) -> ExtractedDoc:
        data = files.read(item.source)
        if data is None:
            raise PermanentError("The uploaded file is missing from storage")
        return extract_pdf_bytes(data)


def extract_pdf_bytes(data: bytes) -> ExtractedDoc:
    import pymupdf  # here, not at the top: it adds about 130 MB to every process that loads it

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise PermanentError("This file couldn't be opened as a PDF") from exc

    with doc:
        if doc.needs_pass:
            raise PermanentError("This PDF is password-protected")
        pages = [PageText(page=i + 1, text=_page_text(page)) for i, page in enumerate(doc)]
        title = _clean_title((doc.metadata or {}).get("title"))
        images = _pdf_figures(doc)
    cover = render_pdf_page(data)
    if cover:
        images.insert(0, ExtractedImage(role="cover", data=cover, page=1))
    return ExtractedDoc(title=title, pages=pages, images=images)


def _pdf_figures(doc: "pymupdf.Document", limit: int = 12) -> list[ExtractedImage]:
    """Pictures embedded in the pages, in reading order, each with the paragraph before it."""
    found: list[ExtractedImage] = []
    for number, page in enumerate(doc, start=1):
        try:
            blocks = page.get_text("dict", sort=True)["blocks"]
        except Exception:
            continue
        previous = None
        for block in blocks:
            if block.get("type") == 0:
                lines = block.get("lines", [])
                text = " ".join(s["text"] for line in lines for s in line["spans"]).strip()
                previous = text or previous
            elif block.get("type") == 1 and block.get("image"):
                if min(block.get("width", 0), block.get("height", 0)) < 150:
                    continue
                found.append(
                    ExtractedImage(role="figure", data=block["image"], page=number, anchor=previous)
                )
                if len(found) == limit:
                    return found
    return found


def _page_text(page: "pymupdf.Page") -> str:
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
