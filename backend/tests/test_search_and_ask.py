import json

import pytest

from app.config import get_settings
from app.models import Item, SourceType
from app.pipeline import process_item
from app.services.answer import (
    NOT_FOUND_MESSAGE,
    answer_question,
    cited_numbers,
    strip_invalid_citations,
)
from app.services.embeddings import HashingEmbedder
from app.services.search import SearchMode, rrf, search
from app.sources import ExtractedDoc, PageText
from tests.helpers import FakeLLM

LIBRARY = {
    "Database indexing": [
        "A hash index maps keys to buckets, so exact-match lookups are very fast.",
        "A B-tree keeps keys sorted, so it also serves range scans and ORDER BY queries.",
    ],
    "Transformers": [
        "The transformer architecture relies on self-attention instead of recurrence.",
        "Positional encodings tell the model the order of the tokens in a sequence.",
    ],
    "Sourdough baking": [
        "A sourdough starter is a culture of wild yeast and lactobacilli.",
        "Bulk fermentation at warm temperatures makes the dough rise faster.",
    ],
}


class StubSource:
    def __init__(self, pages):
        self.pages = pages

    def extract(self, item):
        return ExtractedDoc(title=None, pages=self.pages)


@pytest.fixture
def library(session, monkeypatch):
    # Small chunks without overlap: one chunk per page, so a citation's page can be checked.
    monkeypatch.setattr(get_settings(), "chunk_tokens", 20)
    monkeypatch.setattr(get_settings(), "chunk_overlap", 0)
    # The hashing embedder's similarities run lower than bge's; questions sharing a few words
    # with a passage score about 0.3, unrelated ones 0.
    monkeypatch.setattr(get_settings(), "min_similarity", 0.2)
    ids = {}
    for title, pages in LIBRARY.items():
        item = Item(title=title, source_type=SourceType.pdf, source="unused")
        session.add(item)
        session.flush()
        pages = [PageText(i + 1, text) for i, text in enumerate(pages)]
        process_item(session, item, embedder=HashingEmbedder(), llm=None, source=StubSource(pages))
        ids[title] = item.id
    session.commit()
    return ids


def test_rrf_rewards_agreement():
    fused = rrf([[1, 2, 3], [3, 1, 4]])
    assert [doc for doc, _ in fused] == [1, 3, 2, 4]
    assert fused[0][1] == pytest.approx(1 / 61 + 1 / 62)


@pytest.mark.parametrize("mode", list(SearchMode))
def test_every_mode_finds_the_right_passage(session, library, mode):
    result = search(session, HashingEmbedder(), "which index serves range scans", mode=mode, k=3)
    top = result.passages[0]
    assert top.item_id == library["Database indexing"]
    assert top.page == 2
    assert "range scans" in top.text


def test_keyword_search_ors_the_question_words(session, library):
    # No single passage holds both words; an AND query would return nothing.
    result = search(session, HashingEmbedder(), "sourdough transformer", mode=SearchMode.keyword)
    titles = {p.title for p in result.passages}
    assert titles == {"Sourdough baking", "Transformers"}


def test_unrelated_question_has_low_similarity(session, library):
    result = search(session, HashingEmbedder(), "volcanic eruptions in Iceland")
    assert result.best_similarity < get_settings().min_similarity


def test_citation_helpers():
    assert cited_numbers("A [2]. B [1, 2][7]. C [3]", 3) == [2, 1, 3]
    assert strip_invalid_citations("A [2]. B [1, 9]. C [8]", 3) == "A [2]. B [1]. C "


def test_answer_cites_passages(session, library, monkeypatch):
    monkeypatch.setattr(get_settings(), "answer_k", 2)
    llm = FakeLLM(answer="B-trees keep keys sorted and serve range scans [1]. Not hash [9].")
    result = answer_question(session, HashingEmbedder(), llm, "which index serves range scans?")
    assert not result.not_found
    assert result.cited == [1]
    assert "[9]" not in result.text
    assert result.sources[0].title == "Database indexing"
    # only the top passages went to the model (NFR-6)
    assert len(result.sources) == 2
    assert "range scans" in llm.prompts[0] and "sourdough" not in llm.prompts[0].lower()


def test_unrelated_question_is_not_found_without_calling_the_llm(session, library):
    llm = FakeLLM(answer="made up")
    result = answer_question(session, HashingEmbedder(), llm, "volcanic eruptions in Iceland")
    assert result.not_found and result.text == NOT_FOUND_MESSAGE
    assert llm.prompts == []


def test_model_sentinel_means_not_found(session, library):
    llm = FakeLLM(answer="NOT_FOUND")
    result = answer_question(session, HashingEmbedder(), llm, "how fast is a hash index range scan")
    assert result.not_found and result.text == NOT_FOUND_MESSAGE
    assert llm.prompts  # the gate passed; the model decided


def test_empty_library_is_not_found(session):
    result = answer_question(session, HashingEmbedder(), FakeLLM(), "anything at all")
    assert result.not_found


def _events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_ask_endpoint(client, library, fake_llm):
    fake_llm.answer = "A hash index makes exact-match lookups fast [1]."
    resp = client.post("/ask", json={"question": "what makes exact-match lookups fast?"})
    body = resp.json()
    assert resp.status_code == 200
    assert body["cited"] == [1]
    assert body["sources"][0]["n"] == 1 and body["sources"][0]["page"] == 1
    assert set(body["timings"]) == {"retrieval_ms", "llm_ms", "first_token_ms"}


def test_ask_stream_sends_sources_then_deltas_then_done(client, library, fake_llm):
    fake_llm.answer = "A hash index makes exact-match lookups fast [1]."
    resp = client.post("/ask/stream", json={"question": "what makes exact-match lookups fast?"})
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _events(resp.text)
    kinds = [kind for kind, _ in events]
    assert kinds[0] == "sources" and kinds[-1] == "done"
    assert set(kinds[1:-1]) == {"delta"}
    assert "".join(d["text"] for k, d in events if k == "delta") == fake_llm.answer
    assert events[0][1]["sources"][0]["title"] == "Database indexing"
    assert events[-1][1]["cited"] == [1] and events[-1][1]["not_found"] is False


def test_ask_stream_never_shows_the_sentinel(client, library, fake_llm):
    fake_llm.answer = "NOT_FOUND"
    events = _events(client.post("/ask/stream", json={"question": "hash index speed"}).text)
    assert [k for k, _ in events] == ["sources", "done"]
    assert events[-1][1]["not_found"] is True


def test_ask_stream_reports_llm_errors(client, library, fake_llm):
    from app.services.llm import LLMError

    fake_llm.error = LLMError("Gemini returned 429", retryable=True)
    events = _events(client.post("/ask/stream", json={"question": "hash index"}).text)
    assert events[-1] == ("error", {"message": "Gemini returned 429", "retryable": True})


def test_ask_validates_question(client):
    assert client.post("/ask", json={"question": ""}).status_code == 422


def test_get_chunk(client, library, session):
    result = search(session, HashingEmbedder(), "sourdough starter")
    chunk = client.get(f"/chunks/{result.passages[0].chunk_id}").json()
    assert "starter" in chunk["chunk_text"] and chunk["page"] == 1
    assert client.get("/chunks/999999").status_code == 404
