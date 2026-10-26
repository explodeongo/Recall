"""FastAPI dependencies for the heavy services, so tests can swap in fakes."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.models import User
from app.services.auth import user_for_api_token, user_for_token
from app.services.embeddings import Embedder, get_embedder
from app.services.llm import LLMClient, LLMError, get_llm

SessionDep = Annotated[Session, Depends(get_session)]
SESSION_COOKIE = "recall_session"


def _signed_out(request: Request) -> HTTPException:
    """401 for a request without a valid session. A cookie that no longer matches a session
    (expired, or the account's data was reset) is deleted with it; otherwise the web app's
    "signed in?" check would keep sending the browser back from the log-in page."""
    headers = None
    if request.cookies.get(SESSION_COOKIE):
        secure = "; Secure" if get_settings().cookie_secure else ""
        headers = {
            "set-cookie": f"{SESSION_COOKIE}=; Max-Age=0; Path=/; HttpOnly; SameSite=lax{secure}"
        }
    return HTTPException(401, "Please log in.", headers=headers)


def current_user(request: Request, session: SessionDep) -> User:
    """The signed-in browser's user, or the owner of an "Authorization: Bearer" API token."""
    user = user_for_token(session, request.cookies.get(SESSION_COOKIE))
    if user is None:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() == "bearer":
            user = user_for_api_token(session, token.strip())
    if user is None:
        raise _signed_out(request)
    return user


def browser_user(request: Request, session: SessionDep) -> User:
    """Only a signed-in browser: managing API tokens can't be done with an API token."""
    user = user_for_token(session, request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise _signed_out(request)
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
