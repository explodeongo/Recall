import json
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.deps import CurrentUser, EmbedderDep, LLMDep, SessionDep
from app.schemas import AskIn, AskOut, SourceOut
from app.services.answer import Answer, answer_question, stream_answer
from app.services.images import images_near
from app.services.llm import LLMError
from app.services.search import Passage

router = APIRouter(tags=["ask"])


@router.post("/ask", response_model=AskOut)
def ask(
    body: AskIn, session: SessionDep, user: CurrentUser, embedder: EmbedderDep, llm: LLMDep
) -> AskOut:
    """Answer a question from saved content only, citing the passages used (FR-5, NFR-1)."""
    try:
        result = answer_question(
            session, embedder, llm, body.question, body.mode, user_id=user.id, web=body.web
        )
    except LLMError as exc:
        raise HTTPException(503 if exc.retryable else 502, str(exc)) from exc
    return _ask_out(result, session)


@router.post("/ask/stream")
def ask_stream(
    body: AskIn, session: SessionDep, user: CurrentUser, embedder: EmbedderDep, llm: LLMDep
) -> StreamingResponse:
    """The same answer as Server-Sent Events: `sources`, then `delta`s, then `done`
    (or `error`)."""

    def events() -> Iterator[str]:
        try:
            for kind, payload in stream_answer(
                session, embedder, llm, body.question, body.mode, user_id=user.id, web=body.web
            ):
                if kind == "sources":
                    yield _sse("sources", {"sources": sources_json(payload, session)})
                elif kind == "delta":
                    yield _sse("delta", {"text": payload})
                elif kind == "status":
                    yield _sse("status", {"text": payload})
                else:
                    yield _sse("done", _ask_out(payload).model_dump(exclude={"sources"}))
        except LLMError as exc:
            yield _sse("error", {"message": str(exc), "retryable": exc.retryable})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def sources_json(passages: list[Passage], session=None) -> list[dict]:
    """Sources as sent to the browser (and saved with a chat). With a `session`, each library
    source also lists the figures beside its passage, for the answer to show."""
    out = [
        SourceOut.model_validate({**p.__dict__, "n": n}).model_dump(mode="json")
        for n, p in enumerate(passages, start=1)
    ]
    if session is not None:
        images_near(session, out)
    return out


def _ask_out(answer: Answer, session=None) -> AskOut:
    return AskOut(
        answer=answer.text,
        not_found=answer.not_found,
        web_used=answer.web_used,
        sources=sources_json(answer.sources, session),
        cited=answer.cited,
        timings=answer.timings.as_dict(),
    )
