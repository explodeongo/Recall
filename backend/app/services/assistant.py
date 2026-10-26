"""What AI assistants can do with a library over MCP (app/mcp_server.py): search it, ask it,
read items, browse by tag, and save new things. Plain functions of (session, user, ...), so
they're tested without an MCP client. Answers stay grounded: `ask` uses the library only.
"""

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models import Item, ItemStatus, User
from app.services import connections as connections_service
from app.services.answer import stream_answer
from app.services.embeddings import Embedder
from app.services.library_search import MARK_END, MARK_START, search_items
from app.services.llm import LLMClient
from app.services.tags import has_tags, usage

READ_CHARS = 12_000


def _link(item_id: int) -> str:
    return f"{get_settings().web_url.rstrip('/')}/items/{item_id}"


def _brief(item: Item) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "type": item.source_type.value,
        "source": item.source if item.source_type.value != "note" else None,
        "tags": [t.name for t in item.tags],
        "saved": item.created_at.date().isoformat() if item.created_at else None,
        "status": item.status.value,
        "link": _link(item.id),
    }


def _own(session: Session, user: User, item_id: int) -> Item:
    item = session.get(Item, item_id, options=[selectinload(Item.tags)])
    if item is None or item.user_id != user.id:
        raise ValueError(f"No item {item_id} in this library.")
    return item


def search(session: Session, user: User, embedder: Embedder, query: str, limit: int = 8) -> dict:
    """Items matching the words of `query` anywhere (titles, tags, summaries, notes, full
    text), best first, each with the passage that matched; then items close in topic."""
    found = search_items(session, user.id, query, embedder=embedder, limit=max(1, min(limit, 20)))
    results = []
    for item in found:
        entry = _brief(item)
        match = getattr(item, "match", None)
        if match is not None:
            entry["match"] = match.kind  # "text" or "related"
            entry["passage"] = match.snippet.replace(MARK_START, "").replace(MARK_END, "")
            entry["page"] = match.page
        results.append(entry)
    return {"query": query, "results": results}


def ask(
    session: Session,
    user: User,
    embedder: Embedder,
    llm: LLMClient,
    question: str,
    item_ids: list[int] | None = None,
    tags: list[str] | None = None,
) -> dict:
    """A cited answer from the library only, optionally limited to some items or tags."""
    scope = None
    if item_ids or tags:
        ids = {_own(session, user, i).id for i in item_ids or []}
        if tags:
            ids |= set(
                session.scalars(
                    select(Item.id).where(Item.user_id == user.id, has_tags(tags, "any"))
                )
            )
        scope = sorted(ids) or [-1]
    answer = None
    for kind, payload in stream_answer(
        session, embedder, llm, question, item_ids=scope, user_id=user.id, web=False
    ):
        if kind == "done":
            answer = payload
    sources = [
        {
            "n": n,
            "title": p.title,
            "item_id": p.item_id,
            "page": p.page,
            "text": p.text,
            "link": _link(p.item_id) if p.item_id else p.source,
        }
        for n, p in enumerate(answer.sources, start=1)
        if n in answer.cited
    ]
    return {
        "answer": answer.text,
        "found_in_library": not answer.not_found,
        "sources": sources,
        "note": "Numbers in [brackets] refer to sources. Cite them when you use the answer.",
    }


def get_item(session: Session, user: User, item_id: int) -> dict:
    """An item's summary, key points, tags, the reader's note, and related items."""
    item = _own(session, user, item_id)
    details = item.details or {}
    related = connections_service.connections(session, item, limit=5)
    return {
        **_brief(item),
        "summary": item.summary,
        "overview": details.get("overview"),
        "key_points": details.get("key_points"),
        "note": item.note,
        "related": [
            {"id": c.item.id, "title": c.item.title, "similarity": round(c.similarity, 2)}
            for c in related
        ],
        "error": item.error,
    }


def read_item(session: Session, user: User, item_id: int, start: int = 0) -> dict:
    """Up to READ_CHARS of an item's full text from `start`; call again with `next_start`."""
    item = _own(session, user, item_id)
    if item.status != ItemStatus.ready:
        raise ValueError("Recall hasn't finished reading this item yet.")
    pages = item.content or []
    text = "\n\n".join(
        (f"[page {p['page']}]\n" if p.get("page") else "") + p.get("text", "") for p in pages
    )
    start = max(0, start)
    piece = text[start : start + READ_CHARS]
    end = start + len(piece)
    return {
        "id": item.id,
        "title": item.title,
        "text": piece,
        "start": start,
        "total_chars": len(text),
        "next_start": end if end < len(text) else None,
    }


def list_items(
    session: Session, user: User, tags: list[str] | None = None, limit: int = 20
) -> dict:
    """Recently saved items, newest first, optionally only those carrying every tag given."""
    query = (
        select(Item)
        .options(selectinload(Item.tags))
        .where(Item.user_id == user.id, Item.archived.is_(False), has_tags(tags or [], "all"))
        .order_by(Item.created_at.desc())
        .limit(max(1, min(limit, 50)))
    )
    total = session.scalar(select(func.count(Item.id)).where(Item.user_id == user.id))
    return {"items": [_brief(i) for i in session.scalars(query)], "library_size": total}


def list_tags(session: Session, user: User) -> dict:
    return {"tags": [{"name": t.name, "items": n} for t, n in usage(session, user.id)]}


def save(
    session: Session,
    user: User,
    url: str | None = None,
    note: str | None = None,
    title: str | None = None,
) -> dict:
    """Save a link (article, PDF, YouTube video) or a note. Recall reads it in the background:
    a summary and tags follow within a minute."""
    from app.api.items import create_item

    if (url is None) == (note is None):
        raise ValueError("Give exactly one of url or note.")
    try:
        item = create_item(session=session, user=user, url=url, text=note, title=title)
    except HTTPException as exc:
        raise ValueError(exc.detail) from exc
    return {**_brief(item), "message": "Saved. Recall is reading it now."}
