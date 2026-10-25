from app.models import Highlight, Item


def test_quick_search_finds_titles_passages_tags_and_chats(
    client, library, session, user, fake_llm
):
    fake_llm.answer = "Starters are wild yeast [1]."
    chat_id = client.post("/chats", json={}).json()["id"]
    client.post(f"/chats/{chat_id}/messages", json={"question": "tell me about sourdough"})
    body = client.get("/search", params={"q": "sourdough"}).json()
    assert [i["title"] for i in body["items"]] == ["Sourdough baking"]
    assert body["passages"][0]["title"] == "Sourdough baking"
    assert body["chats"][0]["id"] == chat_id
    tags = client.get("/search", params={"q": "zzz-nothing"}).json()
    assert tags == {"items": [], "passages": [], "highlights": [], "chats": [], "tags": []}


def test_quick_search_finds_highlights_and_notes(client, library, session, user):
    item_id = library["Database indexing"]
    session.add(
        Highlight(
            user_id=user.id, item_id=item_id, start_char=0, end_char=5, quote="A hash", note="exam!"
        )
    )
    session.commit()
    body = client.get("/search", params={"q": "exam"}).json()
    assert body["highlights"][0]["item_title"] == "Database indexing"


def test_quick_search_only_shows_your_own_library(client, anon_client, library, session):
    anon_client.post("/auth/signup", json={"email": "z@example.com", "password": "password1"})
    body = anon_client.get("/search", params={"q": "sourdough"}).json()
    assert body["items"] == [] and body["passages"] == []
    assert session.query(Item).count() == 3
