import json

from app.services.answer import NOT_FOUND_ANYWHERE, _Stream

PICHAI = (
    "Sundar Pichai - Wikipedia",
    "https://en.wikipedia.org/wiki/Sundar_Pichai",
    "Sundar Pichai is the chief executive officer of Alphabet and Google.",
)


def _events(body):
    out = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def _ask(client, question, web=True, chat_id=None):
    chat_id = chat_id or client.post("/chats", json={}).json()["id"]
    resp = client.post(f"/chats/{chat_id}/messages", json={"question": question, "web": web})
    return chat_id, _events(resp.text)


def test_question_outside_the_library_is_answered_from_the_web(client, library, fake_llm, web):
    web.results = [PICHAI]
    fake_llm.answer = "Sundar Pichai is Google's CEO [1]."
    _, events = _ask(client, "volcanic eruptions CEO of Google")  # nothing close in the library
    kinds = [k for k, _ in events]
    assert "status" in kinds
    done = events[-1][1]
    assert done["web_used"] is True and done["not_found"] is False and done["cited"] == [1]
    final_sources = [d for k, d in events if k == "sources"][-1]["sources"]
    assert final_sources[0]["kind"] == "web" and final_sources[0]["source"].startswith("https://")
    assert "web page" in fake_llm.prompts[-1]


def test_partial_library_answer_is_topped_up_from_the_web(client, library, fake_llm, web):
    web.results = [PICHAI]
    fake_llm.replies = [
        "B-trees keep keys sorted for range scans [1].\nMORE: who invented the B-tree",
        "Rudolf Bayer and Edward McCreight invented it [7].",
    ]
    _, events = _ask(client, "which index serves range scans and who invented it?")
    streamed = "".join(d["text"] for k, d in events if k == "delta")
    assert "MORE:" not in streamed  # the hand-off line never reaches the reader
    assert web.queries == ["who invented the B-tree"]
    done = events[-1][1]
    assert "range scans [1]" in done["answer"] and "McCreight" in done["answer"]
    assert done["web_used"] is True
    assert "already answered" in fake_llm.prompts[-1]


def test_nothing_anywhere(client, library, fake_llm, web):
    web.results = []
    _, events = _ask(client, "volcanic eruptions in Iceland")
    assert events[-1][1]["answer"] == NOT_FOUND_ANYWHERE and events[-1][1]["not_found"]


def test_web_off_keeps_library_only_behaviour(client, library, fake_llm, web):
    web.results = [PICHAI]
    _, events = _ask(client, "volcanic eruptions CEO of Google", web=False)
    assert events[-1][1]["not_found"] is True and web.queries == []
    assert fake_llm.prompts == [] or "Follow-up" in fake_llm.prompts[-1]


def test_follow_up_about_the_last_answer_needs_no_new_passages(client, library, fake_llm, web):
    fake_llm.answer = "A hash index makes exact lookups fast [1]."
    chat_id, _ = _ask(client, "what makes exact-match lookups fast?")
    fake_llm.rewrite = "summarize the answer about exact-match lookups in one line"
    fake_llm.answer = "Hash indexes: fast exact lookups [1]."
    _, events = _ask(client, "summarize that in one line", chat_id=chat_id)
    assert events[-1][1]["not_found"] is False
    assert "Earlier in this conversation" in fake_llm.prompts[-1]
    assert web.queries == []  # answered from the conversation, no web needed


def test_ask_endpoint_stays_library_only_unless_asked(client, library, fake_llm, web):
    web.results = [PICHAI]
    body = client.post("/ask", json={"question": "volcanic eruptions CEO of Google"}).json()
    assert body["not_found"] is True and web.queries == []


def test_stream_filter_holds_back_sentinels():
    s = _Stream()
    out = "".join(s.feed(p) for p in ["NOT_", "FOUND"])
    assert out == "" and s.finish()[2] is True

    s = _Stream()
    out = "".join(s.feed(p) for p in ["Answer [1].", "\nMO", "RE: missing part"])
    out += s.rest()
    assert out == "Answer [1].\n" or out.rstrip() == "Answer [1]."
    assert s.finish()[:2] == ("Answer [1].", "missing part")

    s = _Stream()
    out = "".join(s.feed(p) for p in ["Line one.\nMore", "over, line two."])
    assert out + s.rest() == "Line one.\nMoreover, line two."


def test_follow_ups_on_a_document_never_hand_over_to_the_web(client, library, fake_llm, web):
    """A follow-up about something from the user's documents mustn't be answered with
    whatever the web finds under the same name."""
    web.results = [("Another Recall", "https://github.com/someone/recall", "A different app.")]
    fake_llm.answer = "A hash index makes exact lookups fast [1]."
    chat_id, _ = _ask(client, "what makes exact-match lookups fast?")
    fake_llm.rewrite = "what makes exact-match lookups fast with a hash index"  # on topic
    fake_llm.answer = "NOT_FOUND"
    _, events = _ask(client, "tell me more about it", chat_id=chat_id)
    assert web.queries == [] and events[-1][1]["web_used"] is False


def test_removed_citations_leave_no_gaps():
    from app.services.answer import strip_invalid_citations

    assert strip_invalid_citations("Markdown support [7].", 3) == "Markdown support."
    assert strip_invalid_citations("A [9] and B [1].", 3) == "A and B [1]."
