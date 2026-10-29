from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update

from app.config import get_settings
from app.main import app
from app.models import Chunk, Item, ItemStatus, User
from app.services import files
from app.services.llm import DAY_IS_OVER, DailyCap, LLMError
from tests.helpers import FakeLLM
from tests.test_chats import _ask
from tests.test_images import png


@pytest.fixture
def template(client, library, session, fake_llm, monkeypatch):
    """me@example.com's library, used as the demo: a note with a picture, a highlight, a quiz
    and a chat with a cited answer."""
    monkeypatch.setattr(get_settings(), "guest_template_email", "me@example.com")
    session.execute(update(Item).values(status=ItemStatus.ready))
    session.commit()
    indexing = library["Database indexing"]
    assert client.post(f"/items/{indexing}/cards").status_code == 201
    picture = client.post(
        "/images",
        files={"file": ("curve.png", png(), "image/png")},
        data={"item_id": str(indexing), "alt": "A curve"},
    ).json()
    client.put(f"/items/{indexing}/note", json={"note": f"See ![A curve](image:{picture['id']})"})
    session.execute(update(Item).where(Item.id == indexing).values(cover_image_id=picture["id"]))
    session.commit()
    client.post(f"/items/{indexing}/highlights", json={"start_char": 0, "end_char": 20})
    fake_llm.answer = "A B-tree keeps keys sorted, so it serves range scans [1]."
    chat_id = client.post("/chats", json={}).json()["id"]
    _ask(client, chat_id, "which index serves range scans?")
    return {"items": library, "picture": picture["id"]}


def _guest() -> TestClient:
    visitor = TestClient(app)
    resp = visitor.post("/auth/guest")
    assert resp.status_code == 201, resp.text
    assert resp.json()["is_guest"] is True
    return visitor


def test_a_guest_gets_a_private_copy_of_the_demo_library(client, template, session):
    visitor = _guest()
    mine = {i["title"]: i for i in visitor.get("/items").json()}
    assert set(mine) == set(template["items"])
    indexing = mine["Database indexing"]
    assert indexing["id"] != template["items"]["Database indexing"]  # copies, not the originals

    # Search works on the copied passages and vectors.
    hits = visitor.get("/search", params={"q": "B-tree range scans"}).json()["passages"]
    assert hits and all(h["item_id"] in {i["id"] for i in mine.values()} for h in hits)

    # The picture, its place in the note and the cover point at the copy's own picture.
    item = visitor.get(f"/items/{indexing['id']}").json()
    copied = session.scalar(select(Item.cover_image_id).where(Item.id == indexing["id"]))
    assert copied != template["picture"] and f"image:{copied}" in item["note"]
    assert visitor.get(f"/images/{copied}").status_code == 200
    assert visitor.get(f"/images/{template['picture']}").status_code == 404

    # Highlights, cards and the chat came too, the chat's citation pointing at the copy.
    assert len(visitor.get(f"/items/{indexing['id']}/highlights").json()) == 1
    assert len(visitor.get(f"/items/{indexing['id']}/cards").json()) == 2
    chat = visitor.get(f"/chats/{visitor.get('/chats').json()[0]['id']}").json()
    source = chat["messages"][1]["sources"][0]
    assert source["item_id"] == indexing["id"]
    assert session.get(Chunk, source["chunk_id"]).item_id == indexing["id"]

    # Nothing the guest does reaches the template, or another guest.
    visitor.delete(f"/items/{indexing['id']}")
    assert len(client.get("/items").json()) == len(template["items"])
    assert len(_guest().get("/items").json()) == len(template["items"])


def test_the_copy_is_dated_as_if_used_until_yesterday(client, template):
    visitor = _guest()
    newest = max(datetime.fromisoformat(i["created_at"]) for i in visitor.get("/items").json())
    chat = visitor.get("/chats").json()[0]
    assert datetime.fromisoformat(chat["updated_at"]) <= datetime.now(UTC) - timedelta(hours=23)
    assert newest <= datetime.now(UTC) - timedelta(hours=23)


def test_the_template_cant_be_logged_into_and_guests_cant_change_the_account(client, template):
    resp = TestClient(app).post(
        "/auth/login", json={"email": "me@example.com", "password": "hunter22!"}
    )
    assert resp.status_code == 401
    visitor = _guest()
    assert visitor.post("/auth/tokens", json={"name": "x"}).status_code == 403
    assert visitor.post("/auth/delete-account", json={"password": "x"}).status_code == 403
    assert (
        visitor.post(
            "/auth/password", json={"current_password": "x", "new_password": "long enough!"}
        ).status_code
        == 403
    )


def test_guests_have_smaller_daily_limits(client, template, monkeypatch):
    monkeypatch.setattr(get_settings(), "guest_daily_items", 1)
    visitor = _guest()
    assert visitor.post("/items", data={"title": "a", "text": "first note"}).status_code == 202
    resp = visitor.post("/items", data={"title": "b", "text": "second note"})
    assert resp.status_code == 429 and "demo allows 1" in resp.json()["detail"]


def test_guests_are_told_their_smaller_upload_limit(client, template):
    """The Add page shows and checks this, so a guest isn't left uploading a file for nothing."""
    settings = get_settings()
    assert _guest().get("/auth/me").json()["max_upload_mb"] == settings.guest_max_upload_mb
    assert client.get("/auth/me").json()["max_upload_mb"] == settings.max_upload_mb


def test_old_guests_are_removed_but_the_templates_files_stay(client, template, session):
    key = files.save(b"%PDF-1.4 the template's file", ".pdf")
    item_id = template["items"]["Sourdough baking"]
    session.execute(update(Item).where(Item.id == item_id).values(source=key))
    session.commit()
    visitor = _guest()
    copy = next(i for i in visitor.get("/items").json() if i["title"] == "Sourdough baking")
    assert visitor.delete(f"/items/{copy['id']}").status_code == 204
    assert files.read(key) is not None  # still the template's

    session.execute(
        text("UPDATE users SET created_at = now() - interval '25 hours' WHERE is_guest")
    )
    session.commit()
    _guest()
    assert session.scalar(select(func.count(User.id)).where(User.is_guest)) == 1
    assert files.read(key) is not None
    assert visitor.get("/items").status_code == 401  # the old guest's session went with it


def test_no_more_guests_than_the_limit(client, template, session, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_guests", 2)
    for _ in range(4):
        _guest()
    assert session.scalar(select(func.count(User.id)).where(User.is_guest)) == 2


def test_no_demo_without_a_template(client):
    assert TestClient(app).post("/auth/guest").status_code == 404
    assert client.get("/auth/config").json()["guest_demo"] is False


def test_llm_calls_stop_at_the_daily_cap():
    capped = DailyCap(FakeLLM(answer="hi"), cap=2)
    assert capped.generate("one") and capped.generate("two")
    with pytest.raises(LLMError, match="back tomorrow") as err:
        capped.generate("three")
    assert str(err.value) == DAY_IS_OVER
    with pytest.raises(LLMError):
        list(capped.stream("four"))
