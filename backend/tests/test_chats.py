import json

from app.api.chats import answer_note
from app.services.llm import LLMError


def _events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def _ask(client, chat_id, question):
    resp = client.post(f"/chats/{chat_id}/messages", json={"question": question})
    assert resp.headers["content-type"].startswith("text/event-stream")
    return _events(resp.text)


def test_new_chat_is_empty_and_listed(client):
    chat = client.post("/chats", json={}).json()
    assert chat["title"] == "New chat" and chat["messages"] == []
    assert client.get("/chats").json()[0]["message_count"] == 0


def test_first_message_is_answered_saved_and_names_the_chat(client, library, fake_llm):
    fake_llm.answer = "A B-tree keeps keys sorted, so it serves range scans [1]."
    chat_id = client.post("/chats", json={}).json()["id"]
    events = _ask(client, chat_id, "which index serves range scans?")
    kinds = [k for k, _ in events]
    assert kinds[0] == "query" and kinds[1] == "sources" and kinds[-1] == "done"
    assert events[0][1]["query"] == "which index serves range scans?"  # nothing to rewrite yet
    done = events[-1][1]
    assert done["title"] == "which index serves range scans?" and done["cited"] == [1]

    chat = client.get(f"/chats/{chat_id}").json()
    user, reply = chat["messages"]
    assert (user["role"], reply["role"]) == ("user", "assistant")
    assert reply["cited"] == [1] and reply["sources"][0]["title"] == "Database indexing"
    assert client.get("/chats").json()[0]["message_count"] == 2


def test_follow_up_is_rewritten_before_searching(client, library, fake_llm):
    chat_id = client.post("/chats", json={}).json()["id"]
    fake_llm.answer = "B-trees keep keys sorted [1]."
    _ask(client, chat_id, "tell me about B-trees")

    fake_llm.rewrite = "how does sourdough starter culture work"
    fake_llm.answer = "A starter is wild yeast and lactobacilli [1]."
    events = _ask(client, chat_id, "and how does that work?")
    assert events[0][1]["query"] == "how does sourdough starter culture work"
    sources = next(d for k, d in events if k == "sources")["sources"]
    assert sources[0]["title"] == "Sourdough baking"  # the rewrite was searched, not the words
    assert "Earlier in this conversation" in fake_llm.prompts[-1]
    assert "tell me about B-trees" in fake_llm.prompts[-1]


def test_chat_about_one_item_only_searches_it(client, library, fake_llm):
    chat_id = client.post("/chats", json={"item_id": library["Sourdough baking"]}).json()["id"]
    fake_llm.answer = "NOT_FOUND"
    events = _ask(client, chat_id, "which index serves range scans?")
    sources = next(d for k, d in events if k == "sources")["sources"]
    assert {s["title"] for s in sources} <= {"Sourdough baking"}
    listed = client.get("/chats").json()[0]
    assert listed["item_title"] == "Sourdough baking"


def test_failed_answer_leaves_the_chat_unchanged(client, library, fake_llm):
    chat_id = client.post("/chats", json={}).json()["id"]
    fake_llm.error = LLMError("Gemini returned 429", retryable=True)
    events = _ask(client, chat_id, "range scans")
    assert events[-1][0] == "error"
    chat = client.get(f"/chats/{chat_id}").json()
    assert chat["messages"] == [] and chat["title"] == "New chat"


def test_rename_and_delete(client):
    chat_id = client.post("/chats", json={}).json()["id"]
    assert client.patch(f"/chats/{chat_id}", json={"title": "Exam prep"}).json()["title"] == (
        "Exam prep"
    )
    assert client.delete(f"/chats/{chat_id}").status_code == 204
    assert client.get(f"/chats/{chat_id}").status_code == 404


def test_deleting_the_item_keeps_its_chat(client, library):
    item_id = library["Sourdough baking"]
    chat_id = client.post("/chats", json={"item_id": item_id}).json()["id"]
    client.delete(f"/items/{item_id}")
    assert client.get(f"/chats/{chat_id}").json()["item_id"] is None


def test_chat_for_missing_item_is_rejected(client):
    assert client.post("/chats", json={"item_id": 9999}).status_code == 404


def test_saved_sources_keep_their_position_in_the_text(client, library, fake_llm):
    fake_llm.answer = "A starter is wild yeast [1]."
    chat_id = client.post("/chats", json={}).json()["id"]
    _ask(client, chat_id, "what is a sourdough starter?")
    source = client.get(f"/chats/{chat_id}").json()["messages"][1]["sources"][0]
    content = client.get(f"/items/{source['item_id']}/content").json()["pages"]
    joined = "\n\n".join(p["text"] for p in content)
    assert joined[source["start_char"] : source["end_char"]] == source["text"]


def _send(client, chat_id, **body):
    resp = client.post(f"/chats/{chat_id}/messages", json=body)
    return _events(resp.text) if resp.status_code == 200 else resp


def test_pinned_items_and_tags_limit_the_answer(client, session, library, fake_llm):
    from app.models import Item, Tag

    chat_id = client.post("/chats", json={}).json()["id"]
    fake_llm.answer = "NOT_FOUND"
    events = _send(
        client,
        chat_id,
        question="which index serves range scans?",
        item_ids=[library["Sourdough baking"]],
        source="library",
    )
    sources = next(d for k, d in events if k == "sources")["sources"]
    assert {s["title"] for s in sources} <= {"Sourdough baking"}

    asked = client.get(f"/chats/{chat_id}").json()["messages"][0]
    assert asked["context"] == {
        "items": [{"id": library["Sourdough baking"], "title": "Sourdough baking"}],
        "tags": [],
        "source": "library",
    }

    # A tag pins every item carrying it.
    item = session.get(Item, library["Sourdough baking"])
    item.tags = [Tag(name="baking", user_id=item.user_id)]
    session.commit()
    events = _send(client, chat_id, question="which index serves range scans?", tags=["Baking"])
    sources = next(d for k, d in events if k == "sources")["sources"]
    assert {s["title"] for s in sources} <= {"Sourdough baking"}
    # A tag nothing carries leaves nothing to answer from.
    events = _send(client, chat_id, question="range scans?", tags=["nothing"], source="library")
    assert next(d for k, d in events if k == "sources")["sources"] == []

    assert _send(client, chat_id, question="hi", item_ids=[999]).status_code == 404


def test_web_only_skips_the_library(client, library, fake_llm, web):
    web.results = [("Range scans", "https://example.com/b-tree", "B-trees keep keys sorted.")]
    fake_llm.answer = "B-trees keep keys sorted [1]."
    chat_id = client.post("/chats", json={}).json()["id"]
    events = _send(client, chat_id, question="which index serves range scans?", source="web")
    first_sources = next(d for k, d in events if k == "sources")["sources"]
    assert first_sources == []  # no library passages at all
    done = next(d for k, d in events if k == "done")
    assert done["web_used"] and web.queries
    final = [d for k, d in events if k == "sources"][-1]["sources"]
    assert [s["kind"] for s in final] == ["web"]


def test_an_answer_can_be_kept_as_a_note(client, session, library, fake_llm):
    from app.models import Item

    fake_llm.answer = "A B-tree keeps keys sorted [1]."
    chat_id = client.post("/chats", json={}).json()["id"]
    _ask(client, chat_id, "which index serves range scans?")
    answer = client.get(f"/chats/{chat_id}").json()["messages"][1]

    saved = client.post(f"/chats/{chat_id}/messages/{answer['id']}/save")
    assert saved.status_code == 201
    note = saved.json()
    assert note["title"] == "which index serves range scans?" and note["source_type"] == "note"
    item = session.get(Item, note["id"])
    assert item.source.startswith("A B-tree keeps keys sorted [1].")
    assert "Sources:\n[1] Database indexing, page 2" in item.source

    # Saving again gives back the same note, and the chat shows it was saved.
    again = client.post(f"/chats/{chat_id}/messages/{answer['id']}/save").json()
    assert again["id"] == note["id"]
    assert client.get(f"/chats/{chat_id}").json()["messages"][1]["saved_item_id"] == note["id"]
    question = client.get(f"/chats/{chat_id}").json()["messages"][0]
    assert client.post(f"/chats/{chat_id}/messages/{question['id']}/save").status_code == 404


def test_a_saved_answer_numbers_its_sources_in_the_order_it_uses_them():
    sources = [{"title": "One"}, {"title": "Two", "page": 4}, {"title": "Three"}]
    note = answer_note("Keys stay sorted [3]. Pages split [2, 3].", sources, [3, 2])
    assert note.startswith("Keys stay sorted [1]. Pages split [2, 1].")
    assert note.endswith("Sources:\n[1] Three\n[2] Two, page 4")
