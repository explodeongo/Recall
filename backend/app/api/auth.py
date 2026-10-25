from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import SESSION_COOKIE, CurrentUser, SessionDep
from app.models import Item, SourceType, User
from app.schemas import LoginIn, PasswordChange, PasswordConfirm, SignupIn, UserOut
from app.services import auth
from app.services.export import build_export
from app.services.ratelimit import limit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=UserOut, status_code=201)
def signup(body: SignupIn, request: Request, response: Response, session: SessionDep) -> User:
    limit(request, "auth", per_minute=10)
    email = body.email.strip().lower()
    if session.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(409, "An account with that email already exists. Try logging in.")
    first = session.scalar(select(func.count(User.id))) == 0
    user = User(email=email, name=(body.name or "").strip() or None)
    user.password_hash = auth.hash_password(body.password)
    session.add(user)
    session.flush()
    if first:
        auth.claim_unowned(session, user)
    _set_cookie(response, auth.start_session(session, user))
    session.commit()
    return user


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, session: SessionDep) -> User:
    limit(request, "auth", per_minute=10)
    user = session.scalars(select(User).where(User.email == body.email.strip().lower())).first()
    # The same message either way, so the form can't be used to discover who has an account.
    if user is None or not auth.verify_password(body.password, user.password_hash):
        raise HTTPException(401, "That email and password don't match.")
    _set_cookie(response, auth.start_session(session, user))
    session.commit()
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, session: SessionDep) -> Response:
    auth.end_session(session, request.cookies.get(SESSION_COOKIE))
    session.commit()
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.post("/password", status_code=204)
def change_password(
    body: PasswordChange, request: Request, session: SessionDep, user: CurrentUser
) -> Response:
    """Change the password. Other signed-in browsers are signed out; this one stays in."""
    limit(request, "auth", per_minute=10)
    if not auth.verify_password(body.current_password, user.password_hash):
        raise HTTPException(403, "Your current password isn't right.")
    user.password_hash = auth.hash_password(body.new_password)
    auth.end_other_sessions(session, user, request.cookies.get(SESSION_COOKIE))
    session.commit()
    return Response(status_code=204)


@router.post("/delete-account", status_code=204)
def delete_account(
    body: PasswordConfirm, request: Request, session: SessionDep, user: CurrentUser
) -> Response:
    """Delete the account and everything in it, including uploaded files. Can't be undone."""
    limit(request, "auth", per_minute=10)
    if not auth.verify_password(body.password, user.password_hash):
        raise HTTPException(403, "That password isn't right.")
    files = [
        Path(i.source)
        for i in session.scalars(
            select(Item).where(
                Item.user_id == user.id, Item.source_type.in_([SourceType.pdf, SourceType.file])
            )
        )
    ]
    session.delete(user)  # items, chats, tags, highlights, cards and sessions cascade
    session.commit()
    for path in files:
        path.unlink(missing_ok=True)
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/export")
def export(session: SessionDep, user: CurrentUser, files: bool = False) -> Response:
    """Everything in the library as a zip: Markdown, full text, chats and a JSON copy."""
    data = build_export(session, user, include_files=files)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="recall-export-{stamp}.zip"'},
    )


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=auth.SESSION_DAYS * 24 * 3600,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        path="/",
    )
