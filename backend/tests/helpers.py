import json

import pymupdf


def make_pdf(pages: list[list[str]], *, title: str = "", header: str | None = None) -> bytes:
    """Build a real PDF: one list of paragraphs per page, with an optional running header and
    a page-number footer on every page."""
    doc = pymupdf.open()
    for number, paragraphs in enumerate(pages, start=1):
        page = doc.new_page()
        if header:
            page.insert_textbox(pymupdf.Rect(72, 30, 540, 50), header, fontsize=9)
        y = 72
        for para in paragraphs:
            rect = pymupdf.Rect(72, y, 540, y + 200)
            spare = page.insert_textbox(rect, para, fontsize=11)
            y += 200 - spare + 14
        page.insert_textbox(pymupdf.Rect(290, 760, 330, 780), str(number), fontsize=9)
    doc.set_metadata({"title": title})
    return doc.tobytes()


class FakeLLM:
    """Records prompts and returns canned output, so tests need no API key."""

    def __init__(self, entry: dict | None = None, answer: str = "", error: Exception | None = None):
        self.entry = entry or {
            "title": "Database indexing",
            "summary": "Compares B-tree and hash indexes.",
            "tags": ["Databases", "indexing", "databases", "B-Trees!"],
        }
        self.answer = answer
        self.error = error
        self.prompts: list[str] = []

    def generate(self, prompt, *, system=None, json_schema=None):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return json.dumps(self.entry) if json_schema else self.answer

    def stream(self, prompt, *, system=None):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        for i in range(0, len(self.answer), 7):
            yield self.answer[i : i + 7]
