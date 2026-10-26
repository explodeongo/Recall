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
from app.services import images
from app.services.embeddings import Embedder
from app.services.enrich import enrich
from app.services.llm import LLMClient, LLMError
from app.services.text import chunk_pages, clean_pages
from app.sources import Source, get_source

__all__ = ["PermanentError", "process_item"]

MIN_TEXT_CHARS = 50
# How each source type is described to the LLM when it writes the summary.
KINDS = {
    SourceType.youtube: "video transcript",
    SourceType.note: "note",
    SourceType.url: "web page",
}


def process_item(
    session: Session,
    item: Item,
    *,
    embedder: Embedder,
    llm: LLMClient | None,
    source: Source | None = None,
    fetch_image: images.Fetch | None = None,
) -> None:
    """Process one item in place. With `llm=None` the summary and tags are skipped, which the
    retrieval evaluation uses so it can run without an API key."""
    settings = get_settings()
    doc = (source or get_source(item.source_type)).extract(item)
    pages = [p for p in clean_pages(doc.pages) if p.text]
    full_text = "\n\n".join(p.text for p in pages)
    # Notes are whatever the reader typed, however short; other sources need real text.
    too_short = (
        not full_text if item.source_type == SourceType.note else len(full_text) < MIN_TEXT_CHARS
    )
    if too_short:
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
            enrichment = enrich(llm, full_text, existing, KINDS.get(item.source_type, "document"))
        except LLMError as exc:
            if exc.retryable:
                raise
            raise PermanentError(str(exc)) from exc

    if not item.title_edited:  # a title the person gave wins over the page's or the model's
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
    page_starts, offset = {}, 0
    for p in pages:
        if p.page is not None:
            page_starts.setdefault(p.page, offset)
        offset += len(p.text) + 2
    images.attach(session, item, doc.images, full_text, page_starts, fetch_image or _fetch_image)
    if enrichment is not None:
        item.summary = enrichment.summary
        item.details = enrichment.details
        if not item.tags_edited:  # tags the user chose by hand survive reprocessing
            item.tags = get_or_create_tags(session, enrichment.tags, item.user_id)
        item.summary_embedding = embedder.embed_documents([about_text(item)])[0]
    session.flush()


def _fetch_image(url: str) -> bytes | None:
    from app.sources.url import UrlSource

    return UrlSource().fetch_image(url)


def about_text(item: Item) -> str:
    """What an item is about, for its summary embedding."""
    tags = ", ".join(t.name for t in item.tags)
    return f"{item.title}. {item.summary or ''} Topics: {tags}".strip()


def backfill_summary_embeddings(session: Session, embedder: Embedder) -> int:
    """Embed the summaries of items processed before summary embeddings existed."""
    items = list(
        session.scalars(
            select(Item).where(Item.summary.is_not(None), Item.summary_embedding.is_(None))
        )
    )
    if items:
        vectors = embedder.embed_documents([about_text(i) for i in items])
        for item, vector in zip(items, vectors, strict=True):
            item.summary_embedding = vector
        session.commit()
    return len(items)


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
