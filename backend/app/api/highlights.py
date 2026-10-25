from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import CurrentUser, EmbedderDep, SessionDep
from app.models import Highlight, Item
from app.schemas import (
    HighlightIn,
    HighlightNoteIn,
    HighlightOut,
    HighlightWithItem,
    ItemOut,
    NoteIn,
)
from app.services.notes import reindex_notes

router = APIRouter(tags=["highlights and notes"])

MAX_QUOTE = 5000


@router.get("/highlights", response_model=list[HighlightWithItem])
def all_highlights(session: SessionDep, user: CurrentUser, limit: int = 200) -> list[dict]:
    """Every highlight across the library, newest first."""
    rows = session.execute(
        select(Highlight, Item.title)
        .join(Item, Item.id == Highlight.item_id)
        .where(Highlight.user_id == user.id)
        .order_by(Highlight.created_at.desc(), Highlight.id.desc())
        .limit(min(limit, 1000))
    ).all()
    return [{**HighlightOut.model_validate(h).model_dump(), "item_title": t} for h, t in rows]


@router.get("/items/{item_id}/highlights", response_model=list[HighlightOut])
def item_highlights(item_id: int, session: SessionDep, user: CurrentUser) -> list[Highlight]:
    return _item(session, item_id, user.id).highlights


@router.post("/items/{item_id}/highlights", response_model=HighlightOut, status_code=201)
def add_highlight(
    item_id: int, body: HighlightIn, session: SessionDep, user: CurrentUser, embedder: EmbedderDep
) -> Highlight:
    """Highlight a range of the item's full text (the offsets the reader works in)."""
    item = _item(session, item_id, user.id)
    if item.content is None:
        raise HTTPException(409, "This item's text isn't stored yet. Process it again first.")
    text = "\n\n".join(p["text"] for p in item.content)
    if body.end_char > len(text) or body.end_char <= body.start_char:
        raise HTTPException(422, "That range isn't inside the document")
    quote = text[body.start_char : body.end_char].strip()
    if not quote or len(quote) > MAX_QUOTE:
        raise HTTPException(422, f"Highlights must be 1 to {MAX_QUOTE} characters")
    highlight = Highlight(
        user_id=user.id,
        item_id=item.id,
        start_char=body.start_char,
        end_char=body.end_char,
        quote=quote,
        note=_clean(body.note),
    )
    item.highlights.append(highlight)
    session.flush()
    reindex_notes(session, item, embedder)
    session.commit()
    return highlight


@router.patch("/highlights/{highlight_id}", response_model=HighlightOut)
def edit_highlight(
    highlight_id: int,
    body: HighlightNoteIn,
    session: SessionDep,
    user: CurrentUser,
    embedder: EmbedderDep,
) -> Highlight:
    highlight = _highlight(session, highlight_id, user.id)
    highlight.note = _clean(body.note)
    session.flush()
    reindex_notes(session, _item(session, highlight.item_id, user.id), embedder)
    session.commit()
    return highlight


@router.delete("/highlights/{highlight_id}", status_code=204)
def delete_highlight(
    highlight_id: int, session: SessionDep, user: CurrentUser, embedder: EmbedderDep
) -> Response:
    highlight = _highlight(session, highlight_id, user.id)
    item = _item(session, highlight.item_id, user.id)
    item.highlights.remove(highlight)
    session.flush()
    reindex_notes(session, item, embedder)
    session.commit()
    return Response(status_code=204)


@router.put("/items/{item_id}/note", response_model=ItemOut)
def set_note(
    item_id: int, body: NoteIn, session: SessionDep, user: CurrentUser, embedder: EmbedderDep
) -> Item:
    """The reader's own note on an item. It becomes searchable, like the document."""
    item = _item(session, item_id, user.id)
    item.note = _clean(body.note)
    reindex_notes(session, item, embedder)
    session.commit()
    session.refresh(item, ["tags"])
    return item


def _item(session, item_id: int, user_id: int) -> Item:
    item = session.get(
        Item, item_id, options=[selectinload(Item.highlights), selectinload(Item.tags)]
    )
    if item is None or item.user_id != user_id:
        raise HTTPException(404, "Item not found")
    return item


def _highlight(session, highlight_id: int, user_id: int) -> Highlight:
    highlight = session.get(Highlight, highlight_id)
    if highlight is None or highlight.user_id != user_id:
        raise HTTPException(404, "Highlight not found")
    return highlight


def _clean(note: str | None) -> str | None:
    return note.strip() or None if note else None
