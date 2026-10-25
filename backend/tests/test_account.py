import io
import json
import zipfile

from app.models import Card, Highlight, Item, SourceType, User


def _rich_item(session, user) -> Item:
    item = Item(
        user_id=user.id,
        title="Bloom filters",
        source_type=SourceType.url,
        source="https://b.example",
        status="ready",
        summary="Probabilistic sets.",
        details={"overview": "An overview.", "key_points": ["No false negatives."], "sections": []},
        note="Remember for the exam.",
        content=[{"page": None, "text": "Bloom filters never give false negatives."}],
    )
    session.add(item)
    session.flush()
    session.add(
        Highlight(
            user_id=user.id,
            item_id=item.id,
            start_char=0,
            end_char=13,
            quote="Bloom filters",
            note="key term",
        )
    )
    session.add(
        Card(user_id=user.id, item_id=item.id, question="False negatives?", answer="Never.")
    )
    session.commit()
    return item


def test_export_has_markdown_text_chats_and_json(client, session, user):
    _rich_item(session, user)
    resp = client.get("/auth/export")
    assert resp.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert "README.md" in names and "recall.json" in names
    md = zf.read(next(n for n in names if n.startswith("library/"))).decode()
    for expected in (
        "# Bloom filters",
        "## My notes",
        "> Bloom filters",
        "key term",
        "**Q:** False negatives?",
        "No false negatives.",
    ):
        assert expected in md
    data = json.loads(zf.read("recall.json"))
    assert data["items"][0]["highlights"][0]["note"] == "key term"
    assert "embedding" not in json.dumps(data)


def test_export_can_include_uploaded_files(client):
    client.post("/items", files={"file": ("n.md", b"# Notes\n\nhello", "text/markdown")})
    zf = zipfile.ZipFile(io.BytesIO(client.get("/auth/export", params={"files": True}).content))
    uploads = [n for n in zf.namelist() if n.startswith("files/")]
    assert len(uploads) == 1 and zf.read(uploads[0]) == b"# Notes\n\nhello"


def test_change_password(client, anon_client):
    wrong = client.post(
        "/auth/password", json={"current_password": "nope", "new_password": "newpass99"}
    )
    assert wrong.status_code == 403
    other = anon_client  # a second browser signed in to the same account
    other.post("/auth/login", json={"email": "me@example.com", "password": "hunter22!"})
    ok = client.post(
        "/auth/password", json={"current_password": "hunter22!", "new_password": "newpass99"}
    )
    assert ok.status_code == 204
    assert client.get("/auth/me").status_code == 200  # this browser stays in
    assert other.get("/auth/me").status_code == 401  # the other one is signed out
    assert (
        other.post(
            "/auth/login", json={"email": "me@example.com", "password": "newpass99"}
        ).status_code
        == 200
    )


def test_delete_account_removes_everything(client, anon_client, session, user, tmp_path):
    _rich_item(session, user)
    uploaded = client.post("/items", files={"file": ("a.txt", b"some text", "text/plain")}).json()
    stored = list(tmp_path.glob("*.txt"))
    assert stored
    keeper = anon_client
    keeper.post("/auth/signup", json={"email": "keep@example.com", "password": "password1"})
    keeper.post("/items", data={"text": "Not mine to delete."})

    assert client.post("/auth/delete-account", json={"password": "wrong"}).status_code == 403
    assert client.post("/auth/delete-account", json={"password": "hunter22!"}).status_code == 204
    session.expire_all()
    assert session.query(User).filter_by(email="me@example.com").count() == 0
    assert session.get(Item, uploaded["id"]) is None
    assert session.query(Highlight).count() == 0 and session.query(Card).count() == 0
    assert not any(p.exists() for p in stored)
    assert client.get("/auth/me").status_code == 401
    assert [i["title"] for i in keeper.get("/items").json()] == ["Not mine to delete."]
