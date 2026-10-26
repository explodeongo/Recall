import json
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.ask import sources_json
from app.config import get_settings
from app.deps import CurrentUser, EmbedderDep, LLMDep, SessionDep
from app.models import Chat, ChatMessage, Item, SourceType
from app.schemas import ChatCreate, ChatOut, ChatRename, ChatSummary, ItemOut, MessageIn
from app.services import jobs, quota
from app.services.answer import Answer, Turn, stream_answer
from app.services.chat import HISTORY_TURNS, chat_title, standalone_question
from app.services.llm import LLMError
from app.services.ratelimit import limit
from app.services.tags import has_tags

router = APIRouter(prefix="/chats", tags=["chats"])

NEW_CHAT = "New chat"


@router.get("", response_model=list[ChatSummary])
def list_chats(session: SessionDep, user: CurrentUser) -> list[ChatSummary]:
    """Saved chats, most recently used first."""
    count = (
        select(func.count(ChatMessage.id)).where(ChatMessage.chat_id == Chat.id).scalar_subquery()
    )
    rows = session.execute(
        select(Chat, count.label("message_count"), Item.title.label("item_title"))
        .outerjoin(Item, Item.id == Chat.item_id)
        .where(Chat.user_id == user.id)
        .order_by(Chat.updated_at.desc(), Chat.id.desc())
    ).all()
    return [
        ChatSummary(
            id=chat.id,
            title=chat.title,
            item_id=chat.item_id,
            item_title=item_title,
            message_count=message_count,
            updated_at=chat.updated_at,
        )
        for chat, message_count, item_title in rows
    ]


@router.post("", response_model=ChatOut, status_code=201)
def create_chat(body: ChatCreate, session: SessionDep, user: CurrentUser) -> Chat:
    """Start a chat, optionally limited to one item ("ask about this document")."""
    if body.item_id is not None:
        item = session.get(Item, body.item_id)
        if item is None or item.user_id != user.id:
            raise HTTPException(404, "Item not found")
    chat = Chat(user_id=user.id, title=NEW_CHAT, item_id=body.item_id)
    session.add(chat)
    session.commit()
    return _get_or_404(session, chat.id, user.id)


@router.get("/{chat_id}", response_model=ChatOut)
def get_chat(chat_id: int, session: SessionDep, user: CurrentUser) -> Chat:
    return _get_or_404(session, chat_id, user.id)


@router.patch("/{chat_id}", response_model=ChatOut)
def rename_chat(chat_id: int, body: ChatRename, session: SessionDep, user: CurrentUser) -> Chat:
    chat = _get_or_404(session, chat_id, user.id)
    chat.title = body.title.strip()
    session.commit()
    return _get_or_404(session, chat_id, user.id)


@router.delete("/{chat_id}", status_code=204)
def delete_chat(chat_id: int, session: SessionDep, user: CurrentUser) -> Response:
    session.delete(_get_or_404(session, chat_id, user.id))
    session.commit()
    return Response(status_code=204)


@router.post("/{chat_id}/messages")
def send_message(
    chat_id: int,
    body: MessageIn,
    request: Request,
    session: SessionDep,
    user: CurrentUser,
    embedder: EmbedderDep,
    llm: LLMDep,
) -> StreamingResponse:
    """Ask the next question in a chat, streamed as Server-Sent Events: `query` (what was
    searched), `sources`, `delta`s, then `done` with the saved message ids, or `error`.

    Both messages are saved only once the answer is complete, so an interrupted answer leaves
    the chat as it was."""
    limit(request, "ask", per_minute=get_settings().ask_per_minute, key=f"user:{user.id}")
    chat = _get_or_404(session, chat_id, user.id)
    quota.check(session, user.id, "questions", get_settings().daily_questions)
    history = _turns(chat.messages)[-HISTORY_TURNS:]
    context = _context(session, user.id, body)
    if context["items"] or context["tags"]:
        item_ids = _scope(session, user.id, context)
    else:
        item_ids = [chat.item_id] if chat.item_id is not None else None
    source = context["source"]

    def events() -> Iterator[str]:
        try:
            query = standalone_question(llm, history, body.question)
            yield _sse("query", {"query": query})
            answer: Answer | None = None
            for kind, payload in stream_answer(
                session,
                embedder,
                llm,
                body.question,
                search_query=query,
                history=history,
                item_ids=item_ids,
                user_id=user.id,
                web=source != "library",
                library=source != "web",
            ):
                if kind == "sources":
                    yield _sse("sources", {"sources": sources_json(payload, session)})
                elif kind == "status":
                    yield _sse("status", {"text": payload})
                elif kind == "delta":
                    yield _sse("delta", {"text": payload})
                else:
                    answer = payload
        except LLMError as exc:
            yield _sse("error", {"message": str(exc), "retryable": exc.retryable})
            return

        sources = sources_json(answer.sources, session)
        asked = ChatMessage(
            chat_id=chat.id,
            role="user",
            content=body.question,
            search_query=query,
            context=context if context != {"items": [], "tags": [], "source": "both"} else None,
        )
        reply = ChatMessage(
            chat_id=chat.id,
            role="assistant",
            content=answer.text,
            sources=sources,
            cited=answer.cited,
            not_found=answer.not_found,
        )
        session.add_all([asked, reply])
        if chat.title == NEW_CHAT:
            chat.title = chat_title(body.question)
        chat.updated_at = func.now()
        session.commit()
        yield _sse(
            "done",
            {
                "answer": answer.text,
                "not_found": answer.not_found,
                "web_used": answer.web_used,
                "cited": answer.cited,
                "timings": answer.timings.as_dict(),
                "message_ids": [asked.id, reply.id],
                "title": chat.title,
            },
        )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _context(session, user_id: int, body: MessageIn) -> dict:
    """The question's "@" context, checked against the user's library, and its source."""
    items = []
    if body.item_ids:
        rows = session.execute(
            select(Item.id, Item.title).where(Item.id.in_(body.item_ids), Item.user_id == user_id)
        ).all()
        found = {r.id: r.title for r in rows}
        items = [{"id": i, "title": found[i]} for i in dict.fromkeys(body.item_ids) if i in found]
        if not items:
            raise HTTPException(404, "Those items aren't in your library.")
    tags = list(dict.fromkeys(t.strip().lower() for t in body.tags if t.strip()))
    source = body.source or ("both" if body.web else "library")
    return {"items": items, "tags": tags, "source": source}


def _scope(session, user_id: int, context: dict) -> list[int]:
    """Item ids for "@" context: the pinned items and every item carrying a pinned tag."""
    ids = {i["id"] for i in context["items"]}
    if context["tags"]:
        ids |= set(
            session.scalars(
                select(Item.id).where(Item.user_id == user_id, has_tags(context["tags"], "any"))
            )
        )
    return sorted(ids) or [-1]  # a tag nothing carries: nothing to answer from


@router.post("/{chat_id}/messages/{message_id}/save", response_model=ItemOut, status_code=201)
def save_answer(chat_id: int, message_id: int, session: SessionDep, user: CurrentUser) -> Item:
    """Keep an answer in the library as a note: titled with its question, its sources listed
    at the end (so its [n] markers still mean something). Saving it again opens the same note."""
    chat = _get_or_404(session, chat_id, user.id)
    index = next((i for i, m in enumerate(chat.messages) if m.id == message_id), None)
    if index is None or chat.messages[index].role != "assistant":
        raise HTTPException(404, "Answer not found")
    answer = chat.messages[index]
    if answer.not_found:
        raise HTTPException(409, "There's no answer to save here.")
    if answer.saved_item_id is not None:
        saved = session.get(Item, answer.saved_item_id)
        if saved is not None:
            session.refresh(saved, ["tags"])
            return saved
    question = chat.messages[index - 1].content if index > 0 else chat.title
    note = Item(
        user_id=user.id,
        title=question.strip()[:200] or "Saved answer",
        title_edited=True,
        source_type=SourceType.note,
        source=answer_note(answer.content, answer.sources or [], answer.cited or []),
    )
    quota.check(session, user.id, "items", get_settings().daily_items)
    session.add(note)
    session.flush()
    jobs.enqueue(session, note)
    answer.saved_item_id = note.id
    session.commit()
    session.refresh(note, ["tags"])
    return note


def answer_note(text: str, sources: list[dict], cited: list[int]) -> str:
    """An answer as a note: its text, then the sources it cited, numbered as in the text."""
    lines = []
    for n in sorted(set(cited)):
        if not 0 < n <= len(sources):
            continue
        source = sources[n - 1]
        where = source.get("source") if source.get("kind") == "web" else None
        page = f", page {source['page']}" if source.get("page") else ""
        lines.append(f"[{n}] {source.get('title', '')}{page}" + (f" ({where})" if where else ""))
    body = text.strip()
    return body + ("\n\nSources:\n" + "\n".join(lines) if lines else "")


def _turns(messages: list[ChatMessage]) -> list[Turn]:
    turns = []
    for question, answer in zip(messages[::2], messages[1::2], strict=False):
        if question.role == "user" and answer.role == "assistant":
            sources = answer.sources or []
            cited = [sources[n - 1] for n in answer.cited or [] if 0 < n <= len(sources)]
            from_library = any(s.get("kind", "text") != "web" for s in cited)
            turns.append(Turn(question.content, answer.content, from_library))
    return turns


def _get_or_404(session, chat_id: int, user_id: int) -> Chat:
    chat = session.get(
        Chat, chat_id, options=[selectinload(Chat.messages), selectinload(Chat.item)]
    )
    if chat is None or chat.user_id != user_id:
        raise HTTPException(404, "Chat not found")
    return chat


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
