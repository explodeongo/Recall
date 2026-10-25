"""Turns a saved item into chunks, embeddings, a summary and tags (spec section 3.2).

extract → clean → chunk → embed → summarise and tag → save, all in the caller's transaction,
so an item is either fully processed or left as it was.
"""

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import PermanentError
from app.models import Chunk, Item, SourceType, Tag
from app.services.embeddings import Embedder
from app.services.enrich import enrich
from app.services.llm import LLMClient, LLMError
from app.services.text import chunk_pages, clean_pages
from app.sources import Source, get_source

__all__ = ["PermanentError", "process_item"]

MIN_TEXT_CHARS = 50


def process_item(
    session: Session,
    item: Item,
    *,
    embedder: Embedder,
    llm: LLMClient | None,
    source: Source | None = None,
) -> None:
    """Process one item in place. With `llm=None` the summary and tags are skipped, which the
    retrieval evaluation uses so it can run without an API key."""
    settings = get_settings()
    doc = (source or get_source(item.source_type)).extract(item)
    pages = [p for p in clean_pages(doc.pages) if p.text]
    full_text = "\n\n".join(p.text for p in pages)
    if len(full_text) < MIN_TEXT_CHARS:
        if item.source_type == SourceType.pdf:
            raise PermanentError(
                "No text could be read from this PDF. It may be a scanned image, and OCR "
                "isn't supported yet."
            )
        raise PermanentError("The page had too little text to save")

    chunks = chunk_pages(pages, settings.chunk_tokens, settings.chunk_overlap)

    enrichment = None
    if llm is not None:
        existing = list(session.scalars(select(Tag.name).where(Tag.user_id == item.user_id)))
        try:
            enrichment = enrich(llm, full_text, existing)
        except LLMError as exc:
            if exc.retryable:
                raise
            raise PermanentError(str(exc)) from exc

    item.title = doc.title or (enrichment and enrichment.title) or item.title
    # Each chunk is embedded with its document's title in front, so a passage deep inside a
    # long article still carries what the article is about (measured in eval/results.md).
    vectors = embedder.embed_documents([embedding_text(item.title, c.text) for c in chunks])

    # Only the document's own chunks; the reader's note chunks stay (see services/notes.py).
    session.execute(delete(Chunk).where(Chunk.item_id == item.id, Chunk.kind == "text"))
    offsets = locate_chunks(full_text, [c.text for c in chunks])
    session.add_all(
        Chunk(
            item_id=item.id,
            chunk_index=i,
            chunk_text=c.text,
            page=c.page,
            start_char=start,
            end_char=None if start is None else start + len(c.text),
            embedding=v,
        )
        for i, (c, v, start) in enumerate(zip(chunks, vectors, offsets, strict=True))
    )
    item.content = [{"page": p.page, "text": p.text} for p in pages]
    if enrichment is not None:
        item.summary = enrichment.summary
        item.details = enrichment.details
        if not item.tags_edited:  # tags the user chose by hand survive reprocessing
            item.tags = get_or_create_tags(session, enrichment.tags, item.user_id)
    session.flush()


def locate_chunks(full_text: str, chunks: list[str]) -> list[int | None]:
    """Each chunk's start in the full text. Chunks are built in order from that text, so each
    search starts where the previous chunk began (they overlap)."""
    starts: list[int | None] = []
    cursor = 0
    for text in chunks:
        found = full_text.find(text, cursor)
        starts.append(found if found != -1 else None)
        if found != -1:
            cursor = found
    return starts


def embedding_text(title: str, chunk: str) -> str:
    return f"{title}\n\n{chunk}"


def get_or_create_tags(session: Session, names: list[str], user_id: int | None) -> list[Tag]:
    """Each person has their own tags; `user_id` None is the evaluation's unowned library."""
    if not names:
        return []
    # ON CONFLICT keeps two workers tagging at once from tripping the unique constraint.
    session.execute(
        insert(Tag)
        .values([{"name": n, "user_id": user_id} for n in names])
        .on_conflict_do_nothing()
    )
    owner = Tag.user_id.is_(None) if user_id is None else Tag.user_id == user_id
    by_name = {t.name: t for t in session.scalars(select(Tag).where(owner, Tag.name.in_(names)))}
    return [by_name[n] for n in names]
