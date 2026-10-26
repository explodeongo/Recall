from app.config import get_settings
from app.models import Item


def test_files_can_live_in_the_database(client, session, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "file_store", "database")
    pdf = b"%PDF-1.4\n%fake but starts like a pdf\n"
    item = client.post("/items", files={"file": ("a.pdf", pdf, "application/pdf")}).json()
    assert list(tmp_path.iterdir()) == []  # nothing on disk
    assert session.get(Item, item["id"]).source.startswith("db:")
    resp = client.get(f"/items/{item['id']}/file")
    assert resp.content == pdf and resp.headers["content-type"] == "application/pdf"
    assert client.delete(f"/items/{item['id']}").status_code == 204
    from sqlalchemy import text

    assert session.execute(text("SELECT count(*) FROM stored_files")).scalar() == 0


def test_invite_code(anon_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "signup_code", "letmein")
    assert anon_client.get("/auth/config").json() == {"signup_requires_code": True}
    body = {"email": "new@example.com", "password": "password1"}
    assert anon_client.post("/auth/signup", json=body).status_code == 403
    assert (
        anon_client.post("/auth/signup", json={**body, "invite_code": "letmein"}).status_code == 201
    )


def test_daily_limits(client, monkeypatch, fake_llm):
    monkeypatch.setattr(get_settings(), "daily_items", 2)
    monkeypatch.setattr(get_settings(), "daily_questions", 1)
    for _ in range(2):
        assert client.post("/items", data={"text": "a note"}).status_code == 202
    blocked = client.post("/items", data={"text": "one too many"})
    assert blocked.status_code == 429 and "today's limit" in blocked.json()["detail"]

    chat_id = client.post("/chats", json={}).json()["id"]
    fake_llm.answer = "NOT_FOUND"
    assert "event: done" in client.post(f"/chats/{chat_id}/messages", json={"question": "a"}).text
    assert client.post(f"/chats/{chat_id}/messages", json={"question": "b"}).status_code == 429
