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
    pages = clean_pages(doc.pages)
    full_text = "\n\n".join(p.text for p in pages if p.text)
    if len(full_text) < MIN_TEXT_CHARS:
        if item.source_type == SourceType.pdf:
            raise PermanentError(
                "No text could be read from this PDF. It may be a scanned image, and OCR "
                "isn't supported yet."
            )
        raise PermanentError("The page had too little text to save")

    chunks = chunk_pages(pages, settings.chunk_tokens, settings.chunk_overlap)
    vectors = embedder.embed_documents([c.text for c in chunks])

    enrichment = None
    if llm is not None:
        existing = list(session.scalars(select(Tag.name)))
        try:
            enrichment = enrich(llm, full_text, existing)
        except LLMError as exc:
            if exc.retryable:
                raise
            raise PermanentError(str(exc)) from exc

    session.execute(delete(Chunk).where(Chunk.item_id == item.id))
    session.add_all(
        Chunk(item_id=item.id, chunk_index=i, chunk_text=c.text, page=c.page, embedding=v)
        for i, (c, v) in enumerate(zip(chunks, vectors, strict=True))
    )
    item.title = doc.title or (enrichment and enrichment.title) or item.title
    if enrichment is not None:
        item.summary = enrichment.summary
        item.tags = _get_or_create_tags(session, enrichment.tags)
    session.flush()


def _get_or_create_tags(session: Session, names: list[str]) -> list[Tag]:
    if not names:
        return []
    # ON CONFLICT keeps two workers tagging at once from tripping the unique constraint.
    session.execute(insert(Tag).values([{"name": n} for n in names]).on_conflict_do_nothing())
    by_name = {t.name: t for t in session.scalars(select(Tag).where(Tag.name.in_(names)))}
    return [by_name[n] for n in names]
