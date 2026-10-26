from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Item, SourceType
from app.services.auth import hash_password, verify_password


def test_password_hashing_round_trip():
    stored = hash_password("correct horse")
    assert stored.startswith("scrypt$") and "correct horse" not in stored
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong horse", stored)
    assert not verify_password("anything", "not-a-hash")


def test_signup_login_me_logout(client, anon_client):
    assert client.get("/auth/me").json()["email"] == "me@example.com"
    resp = anon_client.post(
        "/auth/login", json={"email": "ME@example.com ", "password": "hunter22!"}
    )
    assert resp.status_code == 200
    assert "recall_session" in resp.cookies
    cookie = resp.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert anon_client.get("/auth/me").status_code == 200
    assert anon_client.post("/auth/logout").status_code == 204
    assert anon_client.get("/auth/me").status_code == 401


def test_wrong_password_and_unknown_email_get_the_same_answer(client, anon_client):
    wrong = anon_client.post(
        "/auth/login", json={"email": "me@example.com", "password": "nope1234"}
    )
    unknown = anon_client.post("/auth/login", json={"email": "who@example.com", "password": "x"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_duplicate_email_and_weak_password_are_rejected(client, anon_client):
    taken = anon_client.post(
        "/auth/signup", json={"email": "me@example.com", "password": "password1"}
    )
    assert taken.status_code == 409
    short = anon_client.post("/auth/signup", json={"email": "new@example.com", "password": "short"})
    assert short.status_code == 422


def test_first_account_claims_items_saved_before_accounts(session):
    session.add(Item(title="Old notes", source_type=SourceType.url, source="https://old"))
    session.commit()
    browser = TestClient(app)  # no account exists yet, so this one is the first
    browser.post("/auth/signup", json={"email": "first@example.com", "password": "password1"})
    assert [i["title"] for i in browser.get("/items").json()] == ["Old notes"]
    item = session.scalars(select(Item)).one()
    session.refresh(item)
    assert item.user_id is not None


def test_login_is_rate_limited(client, anon_client):
    codes = [
        anon_client.post("/auth/login", json={"email": "a@b.co", "password": "x"}).status_code
        for _ in range(12)
    ]
    assert codes[-1] == 429


def test_a_stale_session_cookie_is_cleared(anon_client):
    # e.g. the session expired, or the database was reset since the browser logged in
    anon_client.cookies.set("recall_session", "no-such-session")
    resp = anon_client.get("/items")
    assert resp.status_code == 401
    assert (
        "recall_session=;" in resp.headers["set-cookie"]
        and "Max-Age=0" in resp.headers["set-cookie"]
    )
    # Requests without a cookie aren't told to delete one.
    anon_client.cookies.clear()
    assert "set-cookie" not in anon_client.get("/items").headers
