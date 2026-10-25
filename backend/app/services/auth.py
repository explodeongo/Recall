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

from app.models import Chat, Item, Tag, User, UserSession

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


def claim_unowned(session: Session, user: User) -> None:
    """Give the first account everything saved before accounts existed."""
    for model in (Item, Tag, Chat):
        session.execute(update(model).where(model.user_id.is_(None)).values(user_id=user.id))
