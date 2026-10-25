"""FastAPI dependencies for the heavy services, so tests can swap in fakes."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User
from app.services.auth import user_for_token
from app.services.embeddings import Embedder, get_embedder
from app.services.llm import LLMClient, LLMError, get_llm

SessionDep = Annotated[Session, Depends(get_session)]
SESSION_COOKIE = "recall_session"


def current_user(request: Request, session: SessionDep) -> User:
    user = user_for_token(session, request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise HTTPException(401, "Please log in.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def embedder_dep() -> Embedder:
    return get_embedder()


def llm_dep() -> LLMClient:
    try:
        return get_llm()
    except LLMError as exc:
        raise HTTPException(503, str(exc)) from exc


EmbedderDep = Annotated[Embedder, Depends(embedder_dep)]
LLMDep = Annotated[LLMClient, Depends(llm_dep)]
