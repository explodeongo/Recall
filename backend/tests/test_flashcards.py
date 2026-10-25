from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.models import Card, Item, ItemStatus, SourceType
from app.services.review import Grade, Schedule, describe, locate_quote, next_schedule

TEXT = (
    "A hash index maps keys to buckets, so exact-match lookups are very fast.\n\n"
    "A B-tree keeps keys sorted, so it also serves range scans and ORDER BY queries."
)


def _ready_item(session, user) -> Item:
    item = Item(
        user_id=user.id,
        title="Indexes",
        source_type=SourceType.url,
        source="https://x",
        status=ItemStatus.ready,
        content=[{"page": None, "text": TEXT}],
    )
    session.add(item)
    session.commit()
    return item


def test_scheduling_grows_intervals_and_resets_on_a_miss():
    s = Schedule(0, 2.5, 0, 0)
    s = next_schedule(s, Grade.good)
    assert s.interval_days == 1 and s.reps == 1
    s = next_schedule(s, Grade.good)
    assert s.interval_days == 3
    s = next_schedule(s, Grade.good)
    assert s.interval_days == 7.5
    missed = next_schedule(s, Grade.again)
    assert missed.reps == 0 and missed.lapses == 1 and missed.interval_days < 0.01
    assert missed.ease == 2.3
    assert next_schedule(Schedule(0, 2.5, 0, 0), Grade.easy).interval_days == 4
    assert next_schedule(Schedule(0, 1.35, 0, 0), Grade.hard).ease == 1.3  # floor


def test_interval_labels():
    assert [describe(d) for d in (10 / 1440, 0.5, 1, 45, 400)] == [
        "10m",
        "12h",
        "1d",
        "2mo",
        "1.1y",
    ]


def test_quotes_are_found_despite_case_and_spacing():
    assert locate_quote(TEXT, "exact-match lookups are very fast") == TEXT.index("exact-match")
    assert locate_quote(TEXT, "A  B-TREE keeps keys\nsorted") == TEXT.index("A B-tree")
    assert locate_quote(TEXT, "not in the text at all") is None


def test_quiz_me_makes_cards_linked_to_their_passages(client, session, user):
    item = _ready_item(session, user)
    cards = client.post(f"/items/{item.id}/cards").json()
    assert [c["question"] for c in cards] == [
        "What do hash indexes make fast?",
        "Why can a B-tree serve range scans?",
    ]
    assert TEXT[cards[1]["start_char"] : cards[1]["end_char"]] == "A B-tree keeps keys sorted"
    # asking again doesn't repeat the same questions
    assert client.post(f"/items/{item.id}/cards").status_code == 502


def test_review_flow(client, session, user):
    item = _ready_item(session, user)
    client.post(f"/items/{item.id}/cards")
    due = client.get("/review").json()
    assert len(due) == 2 and due[0]["item_title"] == "Indexes"
    assert due[0]["next"] == {"again": "10m", "hard": "1d", "good": "1d", "easy": "4d"}

    reviewed = client.post(f"/cards/{due[0]['id']}/review", json={"grade": "good"}).json()
    assert reviewed["reps"] == 1
    assert [c["id"] for c in client.get("/review").json()] == [due[1]["id"]]  # first is done
    assert len(client.get("/review", params={"item_id": item.id}).json()) == 2  # quiz me: all

    stats = client.get("/review/stats").json()
    assert stats == {**stats, "due": 1, "total": 2, "reviewed_today": 1, "streak_days": 1}


def test_streak_counts_consecutive_days(client, session, user):
    item = _ready_item(session, user)
    card_id = client.post(f"/items/{item.id}/cards").json()[0]["id"]
    from app.models import Review

    now = datetime.now(UTC)
    for days_ago in (1, 2, 4):  # yesterday and the day before count; 4 days ago is a gap
        session.add(
            Review(
                card_id=card_id,
                user_id=user.id,
                grade="good",
                reviewed_at=now - timedelta(days=days_ago),
            )
        )
    session.commit()
    assert client.get("/review/stats").json()["streak_days"] == 2


def test_cards_are_private_and_editable(client, anon_client, session, user):
    item = _ready_item(session, user)
    card = client.post(f"/items/{item.id}/cards").json()[0]
    edited = client.patch(f"/cards/{card['id']}", json={"answer": "Exact lookups."}).json()
    assert edited["answer"] == "Exact lookups."
    anon_client.post("/auth/signup", json={"email": "q@example.com", "password": "password1"})
    assert anon_client.get("/review").json() == []
    assert (
        anon_client.post(f"/cards/{card['id']}/review", json={"grade": "good"}).status_code == 404
    )
    assert client.delete(f"/cards/{card['id']}").status_code == 204
    session.execute(update(Card).values(due_at=datetime.now(UTC)))
    session.commit()
    assert len(client.get("/review").json()) == 1


def test_unready_items_cant_be_quizzed(client, session, user):
    item = Item(user_id=user.id, title="t", source_type=SourceType.url, source="https://x")
    session.add(item)
    session.commit()
    assert client.post(f"/items/{item.id}/cards").status_code == 409
