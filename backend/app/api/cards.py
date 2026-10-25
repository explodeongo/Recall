from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.deps import CurrentUser, LLMDep, SessionDep
from app.models import Card, Item, ItemStatus, Review
from app.pipeline import KINDS
from app.schemas import CardEdit, CardOut, DueCard, GradeIn, ReviewStats
from app.services.llm import LLMError
from app.services.ratelimit import limit
from app.services.review import Grade, Schedule, describe, due_after, make_cards, next_schedule

router = APIRouter(tags=["flashcards"])


@router.post("/items/{item_id}/cards", response_model=list[CardOut], status_code=201)
def generate_cards(
    item_id: int, request: Request, session: SessionDep, user: CurrentUser, llm: LLMDep
) -> list[Card]:
    """Make flashcards from an item ("quiz me"). Asking again adds new ones, not repeats."""
    limit(request, "cards", per_minute=6, key=f"user:{user.id}")
    item = session.get(Item, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(404, "Item not found")
    if item.status != ItemStatus.ready or not item.content:
        raise HTTPException(409, "This item isn't ready yet, or its text isn't stored.")
    existing = list(session.scalars(select(Card.question).where(Card.item_id == item.id)))
    text = "\n\n".join(p["text"] for p in item.content)
    try:
        made = make_cards(
            llm, text, kind=KINDS.get(item.source_type, "document"), existing=existing
        )
    except LLMError as exc:
        raise HTTPException(503 if exc.retryable else 502, str(exc)) from exc
    if not made:
        raise HTTPException(502, "Couldn't make new flashcards from this item. Try again.")
    cards = [
        Card(
            user_id=user.id,
            item_id=item.id,
            question=c.question,
            answer=c.answer,
            start_char=c.start_char,
            end_char=c.end_char,
        )
        for c in made
    ]
    session.add_all(cards)
    session.commit()
    return cards


@router.get("/items/{item_id}/cards", response_model=list[CardOut])
def item_cards(item_id: int, session: SessionDep, user: CurrentUser) -> list[Card]:
    return list(
        session.scalars(
            select(Card).where(Card.item_id == item_id, Card.user_id == user.id).order_by(Card.id)
        )
    )


@router.patch("/cards/{card_id}", response_model=CardOut)
def edit_card(card_id: int, body: CardEdit, session: SessionDep, user: CurrentUser) -> Card:
    card = _card(session, card_id, user.id)
    if body.question is not None:
        card.question = body.question.strip()
    if body.answer is not None:
        card.answer = body.answer.strip()
    session.commit()
    return card


@router.delete("/cards/{card_id}", status_code=204)
def delete_card(card_id: int, session: SessionDep, user: CurrentUser) -> Response:
    session.delete(_card(session, card_id, user.id))
    session.commit()
    return Response(status_code=204)


@router.get("/review", response_model=list[DueCard])
def due_cards(
    session: SessionDep, user: CurrentUser, item_id: int | None = None, limit_: int = 50
) -> list[dict]:
    """Cards to review now. With `item_id`, every card from that item ("quiz me on this"),
    due or not."""
    query = select(Card).options(selectinload(Card.item)).where(Card.user_id == user.id)
    if item_id is not None:
        query = query.where(Card.item_id == item_id).order_by(Card.due_at, Card.id)
    else:
        query = query.where(Card.due_at <= func.now()).order_by(Card.due_at, Card.id)
    now = datetime.now(UTC)
    return [_due(card, now) for card in session.scalars(query.limit(min(limit_, 200)))]


@router.post("/cards/{card_id}/review", response_model=CardOut)
def review_card(card_id: int, body: GradeIn, session: SessionDep, user: CurrentUser) -> Card:
    card = _card(session, card_id, user.id)
    now = datetime.now(UTC)
    schedule = next_schedule(_schedule(card), body.grade)
    card.interval_days = schedule.interval_days
    card.ease = schedule.ease
    card.reps = schedule.reps
    card.lapses = schedule.lapses
    card.due_at = due_after(schedule, now)
    card.last_reviewed_at = now
    session.add(Review(card_id=card.id, user_id=user.id, grade=body.grade))
    session.commit()
    return card


@router.get("/review/stats", response_model=ReviewStats)
def review_stats(session: SessionDep, user: CurrentUser, tz_offset: int = 0) -> ReviewStats:
    """`tz_offset` is the browser's minutes east of UTC, so "today" and the streak follow the
    reader's own days."""
    shift = timedelta(minutes=tz_offset)
    today = (datetime.now(UTC) + shift).date()
    due = session.scalar(
        select(func.count(Card.id)).where(Card.user_id == user.id, Card.due_at <= func.now())
    )
    total = session.scalar(select(func.count(Card.id)).where(Card.user_id == user.id))
    next_due = session.scalar(
        select(func.min(Card.due_at)).where(Card.user_id == user.id, Card.due_at > func.now())
    )
    since = datetime.now(UTC) - timedelta(days=400)
    times = session.scalars(
        select(Review.reviewed_at).where(Review.user_id == user.id, Review.reviewed_at >= since)
    ).all()
    # The database may hand back times in its own zone; put them in the reader's.
    local = [(t.astimezone(UTC) + shift).date() for t in times]
    days = set(local)
    reviewed_today = sum(1 for d in local if d == today)
    streak = 0
    day = today if today in days else today - timedelta(days=1)  # today isn't over yet
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return ReviewStats(
        due=due or 0,
        total=total or 0,
        reviewed_today=reviewed_today,
        streak_days=streak,
        next_due_at=next_due,
    )


def _schedule(card: Card) -> Schedule:
    return Schedule(card.interval_days, card.ease, card.reps, card.lapses)


def _due(card: Card, now: datetime) -> dict:
    current = _schedule(card)
    return {
        **CardOut.model_validate(card).model_dump(),
        "item_title": card.item.title,
        "next": {g.value: describe(next_schedule(current, g).interval_days) for g in Grade},
    }


def _card(session, card_id: int, user_id: int) -> Card:
    card = session.get(Card, card_id)
    if card is None or card.user_id != user_id:
        raise HTTPException(404, "Card not found")
    return card
