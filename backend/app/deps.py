"""FastAPI dependencies for the heavy services, so tests can swap in fakes."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User
from app.services.auth import user_for_api_token, user_for_token
from app.services.embeddings import Embedder, get_embedder
from app.services.llm import LLMClient, LLMError, get_llm

SessionDep = Annotated[Session, Depends(get_session)]
SESSION_COOKIE = "recall_session"


def current_user(request: Request, session: SessionDep) -> User:
    """The signed-in browser's user, or the owner of an "Authorization: Bearer" API token."""
    user = user_for_token(session, request.cookies.get(SESSION_COOKIE))
    if user is None:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() == "bearer":
            user = user_for_api_token(session, token.strip())
    if user is None:
        raise HTTPException(401, "Please log in.")
    return user


def browser_user(request: Request, session: SessionDep) -> User:
    """Only a signed-in browser: managing API tokens can't be done with an API token."""
    user = user_for_token(session, request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise HTTPException(401, "Please log in.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
BrowserUser = Annotated[User, Depends(browser_user)]


def embedder_dep() -> Embedder:
    return get_embedder()


def llm_dep() -> LLMClient:
    try:
        return get_llm()
    except LLMError as exc:
        raise HTTPException(503, str(exc)) from exc


EmbedderDep = Annotated[Embedder, Depends(embedder_dep)]
LLMDep = Annotated[LLMClient, Depends(llm_dep)]
