import re

import pytest

from app import worker
from app.errors import PermanentError
from app.models import Chunk, Item, ItemStatus, SourceType, Tag
from app.pipeline import process_item
from app.services import jobs
from app.services.embeddings import HashingEmbedder
from app.services.llm import LLMError
from app.sources import ExtractedDoc, PageText
from tests.helpers import FakeLLM, make_pdf


class StubSource:
    def __init__(self, doc: ExtractedDoc):
        self.doc = doc

    def extract(self, item):
        return self.doc


DOC = ExtractedDoc(
    title=None,
    pages=[
        PageText(1, "Hash indexes map keys to buckets. They are fast for exact lookups."),
        PageText(2, "B-trees keep keys sorted, so they also serve range scans and ORDER BY."),
    ],
)


def _item(session, source_type=SourceType.pdf, source="unused") -> Item:
    item = Item(title="indexing notes", source_type=source_type, source=source)
    session.add(item)
    session.commit()
    return item


def test_process_item_saves_chunks_summary_and_tags(session):
    item = _item(session)
    llm = FakeLLM()
    process_item(session, item, embedder=HashingEmbedder(), llm=llm, source=StubSource(DOC))
    session.commit()

    item = session.get(Item, item.id)
    assert item.title == "Database indexing"  # no title in the source, so the model's is used
    assert item.summary == "Compares B-tree and hash indexes."
    assert [t.name for t in item.tags] == ["databases", "indexing", "b-trees"]
    chunks = session.query(Chunk).filter_by(item_id=item.id).all()
    assert len(chunks) == 1 and chunks[0].page == 1
    assert len(chunks[0].embedding) == 384
    assert "B-trees keep keys sorted" in chunks[0].chunk_text


def test_existing_tags_are_offered_and_reused(session):
    session.add(Tag(name="databases"))
    session.commit()
    item = _item(session)
    llm = FakeLLM()
    process_item(session, item, embedder=HashingEmbedder(), llm=llm, source=StubSource(DOC))
    session.commit()
    assert "databases" in llm.prompts[0]
    assert session.query(Tag).filter_by(name="databases").count() == 1


def test_source_title_wins_over_model_title(session):
    item = _item(session)
    doc = ExtractedDoc(title="Indexing 101", pages=DOC.pages)
    process_item(session, item, embedder=HashingEmbedder(), llm=FakeLLM(), source=StubSource(doc))
    assert item.title == "Indexing 101"


def test_reprocessing_replaces_chunks(session):
    item = _item(session)
    for _ in range(2):
        process_item(
            session, item, embedder=HashingEmbedder(), llm=FakeLLM(), source=StubSource(DOC)
        )
        session.commit()
    assert session.query(Chunk).filter_by(item_id=item.id).count() == 1


def test_without_llm_only_chunks_are_saved(session):
    item = _item(session)
    process_item(session, item, embedder=HashingEmbedder(), llm=None, source=StubSource(DOC))
    assert item.summary is None and item.tags == []
    assert session.query(Chunk).filter_by(item_id=item.id).count() == 1


def test_scanned_pdf_fails_with_a_clear_message(session):
    item = _item(session)
    empty = ExtractedDoc(title=None, pages=[PageText(1, ""), PageText(2, "3")])
    with pytest.raises(PermanentError, match="scanned"):
        process_item(
            session, item, embedder=HashingEmbedder(), llm=FakeLLM(), source=StubSource(empty)
        )


def test_non_retryable_llm_error_becomes_permanent(session):
    item = _item(session)
    llm = FakeLLM(error=LLMError("GEMINI_API_KEY is not set"))
    with pytest.raises(PermanentError, match="GEMINI_API_KEY"):
        process_item(session, item, embedder=HashingEmbedder(), llm=llm, source=StubSource(DOC))


def test_worker_processes_a_real_pdf_end_to_end(session, tmp_path):
    pdf = tmp_path / "notes.pdf"
    pdf.write_bytes(
        make_pdf(
            [["Hash indexes give constant-time exact lookups."], ["B-trees support ranges."]],
            header="CS 501 - Databases",
        )
    )
    item = _item(session, source=str(pdf))
    jobs.enqueue(session, item)
    session.commit()

    assert worker.run_once(HashingEmbedder(), FakeLLM()) is True
    session.expire_all()
    item = session.get(Item, item.id)
    assert item.status == ItemStatus.ready and item.error is None
    pages = [c.page for c in item.chunks]
    assert pages == [1]
    assert "CS 501" in item.chunks[0].chunk_text  # two pages: too few to call it a header
    assert worker.run_once(HashingEmbedder(), FakeLLM()) is False


def test_worker_marks_unreadable_item_failed(session, tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(make_pdf([[], [], []]))
    item = _item(session, source=str(pdf))
    jobs.enqueue(session, item)
    session.commit()

    worker.run_once(HashingEmbedder(), FakeLLM())
    session.expire_all()
    item = session.get(Item, item.id)
    assert item.status == ItemStatus.failed
    assert "scanned image" in item.error


def test_detailed_summary_is_saved(session):
    item = _item(session)
    process_item(session, item, embedder=HashingEmbedder(), llm=FakeLLM(), source=StubSource(DOC))
    assert item.details["overview"] == "An overview of two index structures."
    assert len(item.details["key_points"]) == 2
    assert item.details["sections"][0]["heading"] == "Hash indexes"


def test_hand_edited_tags_survive_reprocessing(session):
    item = _item(session)
    item.tags = [Tag(name="my reading")]
    item.tags_edited = True
    session.commit()
    process_item(session, item, embedder=HashingEmbedder(), llm=FakeLLM(), source=StubSource(DOC))
    assert [t.name for t in item.tags] == ["my reading"]


def test_long_documents_are_sampled_from_start_middle_and_end():
    from app.services.enrich import GAP, sample_text

    paragraphs = [f"Paragraph {i}. " + "word " * 40 for i in range(400)]
    text = "\n\n".join(paragraphs)
    sample = sample_text(text, 8000)
    assert len(sample) <= 8000
    assert sample.count(GAP) == 3
    assert "Paragraph 0." in sample and "Paragraph 399." in sample
    middle = [int(n) for n in re.findall(r"Paragraph (\d+)\.", sample) if 100 < int(n) < 300]
    assert middle  # excerpts from the middle third, not only the two ends
    assert sample_text("short", 8000) == "short"


def test_full_text_and_chunk_positions_are_stored(session, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "chunk_tokens", 20)
    monkeypatch.setattr(get_settings(), "chunk_overlap", 5)
    item = _item(session)
    process_item(session, item, embedder=HashingEmbedder(), llm=None, source=StubSource(DOC))
    assert [p["page"] for p in item.content] == [1, 2]
    joined = "\n\n".join(p["text"] for p in item.content)
    chunks = session.query(Chunk).filter_by(item_id=item.id).order_by(Chunk.chunk_index).all()
    assert len(chunks) > 1
    for c in chunks:
        assert joined[c.start_char : c.end_char] == c.chunk_text


def test_locate_chunks_handles_overlap_and_misses():
    from app.pipeline import locate_chunks

    text = "one two three. four five six. seven eight."
    assert locate_chunks(text, ["one two three.", "three. four five six.", "nowhere"]) == [
        0,
        8,
        None,
    ]
