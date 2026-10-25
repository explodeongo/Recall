import json

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
