from fastapi import APIRouter, Query
from sqlalchemy import or_, select

from app.config import get_settings
from app.deps import CurrentUser, EmbedderDep, SessionDep
from app.models import Chat, ChatMessage, Highlight, Item, Tag
from app.schemas import SearchOut
from app.services.search import search

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchOut)
def quick_search(
    session: SessionDep,
    user: CurrentUser,
    embedder: EmbedderDep,
    q: str = Query(min_length=1, max_length=200),
) -> dict:
    """Everything that matches, for the ⌘K box: documents by title, passages by meaning and
    keywords (hybrid search, no LLM), highlights and notes, chats and tags."""
    like = f"%{q.strip()}%"
    items = session.scalars(
        select(Item)
        .where(Item.user_id == user.id, Item.title.ilike(like))
        .order_by(Item.created_at.desc())
        .limit(5)
    ).all()

    passages = []
    if len(q.strip()) >= 3:
        found = search(session, embedder, q, k=12, candidate_k=20, user_id=user.id)
        relevant = (found.best_similarity or 0) >= get_settings().min_similarity
        seen: set[int] = set()
        for p in found.passages if relevant else []:
            if p.item_id in seen:  # one passage per document keeps the list varied
                continue
            seen.add(p.item_id)
            passages.append(
                {
                    "item_id": p.item_id,
                    "title": p.title,
                    "text": p.text[:300],
                    "page": p.page,
                    "start_char": p.start_char,
                    "end_char": p.end_char,
                    "kind": p.kind,
                }
            )
            if len(passages) == 5:
                break

    highlights = session.execute(
        select(Highlight, Item.title)
        .join(Item, Item.id == Highlight.item_id)
        .where(
            Highlight.user_id == user.id,
            or_(Highlight.quote.ilike(like), Highlight.note.ilike(like)),
        )
        .order_by(Highlight.created_at.desc())
        .limit(5)
    ).all()
    chats = session.scalars(
        select(Chat)
        .where(
            Chat.user_id == user.id,
            or_(
                Chat.title.ilike(like),
                Chat.messages.any(ChatMessage.content.ilike(like)),
            ),
        )
        .order_by(Chat.updated_at.desc())
        .limit(5)
    ).all()
    tags = session.scalars(
        select(Tag).where(Tag.user_id == user.id, Tag.name.ilike(like)).order_by(Tag.name).limit(5)
    ).all()

    return {
        "items": [
            {"id": i.id, "title": i.title, "source_type": i.source_type, "status": i.status}
            for i in items
        ],
        "passages": passages,
        "highlights": [
            {
                "id": h.id,
                "item_id": h.item_id,
                "item_title": title,
                "quote": h.quote[:300],
                "note": h.note,
                "start_char": h.start_char,
                "end_char": h.end_char,
            }
            for h, title in highlights
        ],
        "chats": [{"id": c.id, "title": c.title} for c in chats],
        "tags": [t.name for t in tags],
    }
