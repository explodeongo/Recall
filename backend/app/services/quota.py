"""Daily limits per person, so one account on a public deployment can't use up the LLM quota.

Counted from the database (what was saved or asked since midnight UTC), so they hold across
restarts and API processes.
"""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Card, Chat, ChatMessage, Item


def _since_midnight() -> datetime:
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def check(session: Session, user_id: int, kind: str, limit: int) -> None:
    since = _since_midnight()
    if kind == "items":
        used = select(func.count(Item.id)).where(Item.user_id == user_id, Item.created_at >= since)
    elif kind == "questions":
        used = (
            select(func.count(ChatMessage.id))
            .join(Chat, Chat.id == ChatMessage.chat_id)
            .where(
                Chat.user_id == user_id,
                ChatMessage.role == "user",
                ChatMessage.created_at >= since,
            )
        )
    else:  # quizzes: batches of cards made today
        used = select(func.count(func.distinct(Card.created_at))).where(
            Card.user_id == user_id, Card.created_at >= since
        )
    if (session.scalar(used) or 0) >= limit:
        raise HTTPException(
            429, f"You've reached today's limit for this ({limit}). It resets at midnight UTC."
        )
