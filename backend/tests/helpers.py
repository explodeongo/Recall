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

    def __init__(
        self,
        entry: dict | None = None,
        answer: str = "",
        error: Exception | None = None,
        rewrite: str | None = None,
    ):
        self.entry = entry or {
            "title": "Database indexing",
            "summary": "Compares B-tree and hash indexes.",
            "overview": "An overview of two index structures.",
            "key_points": ["Hash indexes are fast for exact lookups.", "B-trees support ranges."],
            "sections": [{"heading": "Hash indexes", "body": "Buckets and exact lookups."}],
            "tags": ["Databases", "indexing", "databases", "B-Trees!"],
        }
        self.answer = answer
        self.error = error
        self.rewrite = rewrite  # reply to a follow-up rewrite request
        self.replies: list[str] = []  # answers for successive streamed calls, then `answer`
        self.cards = [
            {
                "question": "What do hash indexes make fast?",
                "answer": "Exact-match lookups.",
                "quote": "exact-match lookups are very fast",
            },
            {
                "question": "Why can a B-tree serve range scans?",
                "answer": "It keeps keys sorted.",
                "quote": "A B-tree keeps keys sorted",
            },
        ]
        self.prompts: list[str] = []
        self.systems: list[str | None] = []

    def generate(self, prompt, *, system=None, json_schema=None):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        if "flashcards" in prompt and json_schema:
            return json.dumps({"cards": self.cards})
        if "Follow-up question:" in prompt:
            return self.rewrite or prompt.split("Follow-up question: ", 1)[1].split("\n", 1)[0]
        return json.dumps(self.entry) if json_schema else self.answer

    def stream(self, prompt, *, system=None):
        self.prompts.append(prompt)
        self.systems.append(system)
        if self.error:
            raise self.error
        answer = self.replies.pop(0) if self.replies else self.answer
        for i in range(0, len(answer), 7):
            yield answer[i : i + 7]


class FakeSearcher:
    """Web search with canned results; pages are 'read' as their snippets."""

    def __init__(self, results=None):
        self.results = list(results or [])  # (title, url, snippet) tuples
        self.queries: list[str] = []

    def search(self, query, n):
        from app.services.web import WebResult

        self.queries.append(query)
        return [WebResult(*r) for r in self.results[:n]]
