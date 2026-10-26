"""Passwords and sign-in sessions.

Passwords are hashed with scrypt (memory-hard, in the standard library). A session is a random
token in an HttpOnly cookie; the database keeps only its SHA-256, so a leaked database can't be
used to sign in.
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import ApiToken, Chat, Item, Tag, User, UserSession

SESSION_DAYS = 30
_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, maxmem=64 * 2**20)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        candidate = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            maxmem=64 * 2**20,
        )
    except ValueError:
        return False
    return hmac.compare_digest(candidate.hex(), digest)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(session: Session, user: User) -> str:
    """Create a session and return the token to put in the cookie."""
    token = secrets.token_urlsafe(32)
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=_token_hash(token),
            expires_at=datetime.now(UTC) + timedelta(days=SESSION_DAYS),
        )
    )
    return token


def user_for_token(session: Session, token: str | None) -> User | None:
    if not token:
        return None
    row = session.scalars(
        select(UserSession).where(
            UserSession.token_hash == _token_hash(token),
            UserSession.expires_at > datetime.now(UTC),
        )
    ).first()
    return row.user if row else None


def end_session(session: Session, token: str | None) -> None:
    if token:
        session.execute(delete(UserSession).where(UserSession.token_hash == _token_hash(token)))


def end_other_sessions(session: Session, user: User, keep_token: str | None) -> None:
    keep = _token_hash(keep_token) if keep_token else ""
    session.execute(
        delete(UserSession).where(UserSession.user_id == user.id, UserSession.token_hash != keep)
    )


def claim_unowned(session: Session, user: User) -> None:
    """Give the first account everything saved before accounts existed."""
    for model in (Item, Tag, Chat):
        session.execute(update(model).where(model.user_id.is_(None)).values(user_id=user.id))


API_TOKEN_PREFIX = "rcl_"


def create_api_token(session: Session, user: User, name: str) -> tuple[ApiToken, str]:
    """A new personal access token; returns the row and the token, which isn't kept."""
    token = API_TOKEN_PREFIX + secrets.token_urlsafe(32)
    row = ApiToken(user_id=user.id, name=name, token_hash=_token_hash(token), prefix=token[:10])
    session.add(row)
    return row, token


def user_for_api_token(session: Session, token: str | None) -> User | None:
    """The token's owner, noting when it was last used (at most once a minute)."""
    if not token or not token.startswith(API_TOKEN_PREFIX):
        return None
    row = session.scalars(select(ApiToken).where(ApiToken.token_hash == _token_hash(token))).first()
    if row is None:
        return None
    now = datetime.now(UTC)
    if row.last_used_at is None or now - row.last_used_at > timedelta(minutes=1):
        row.last_used_at = now
        session.commit()
    return row.user
