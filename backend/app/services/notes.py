"""Your own notes as part of the library.

An item's note and the notes on its highlights are kept as extra "note" chunks, embedded like
the document's own text, so Ask can find and cite them. They're rebuilt whenever a note or
highlight changes, and left alone when the document itself is processed again.
"""

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Chunk, Item
from app.pipeline import embedding_text
from app.services.embeddings import Embedder
from app.services.images import strip_tokens
from app.services.text import chunk_pages
from app.sources import PageText


def notes_text(item: Item) -> str:
    parts = []
    if item.note and item.note.strip():
        parts.append(strip_tokens(item.note).strip())
    for h in item.highlights:
        if h.note and h.note.strip():
            parts.append(f'On the passage "{h.quote.strip()}": {h.note.strip()}')
    return "\n\n".join(parts)


def reindex_notes(session: Session, item: Item, embedder: Embedder) -> None:
    settings = get_settings()
    session.execute(delete(Chunk).where(Chunk.item_id == item.id, Chunk.kind == "note"))
    text = notes_text(item)
    if not text:
        return
    chunks = chunk_pages([PageText(None, text)], settings.chunk_tokens, settings.chunk_overlap)
    heading = f"My notes on {item.title}"
    vectors = embedder.embed_documents([embedding_text(heading, c.text) for c in chunks])
    session.add_all(
        Chunk(item_id=item.id, chunk_index=-(i + 1), chunk_text=c.text, kind="note", embedding=v)
        for i, (c, v) in enumerate(zip(chunks, vectors, strict=True))
    )
