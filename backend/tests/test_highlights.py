import json

from app.models import Chunk, Item, SourceType
from app.pipeline import process_item
from app.services.embeddings import HashingEmbedder
from app.sources import ExtractedDoc, PageText

TEXT = "Bloom filters are probabilistic.\n\nThey never give false negatives."


def _item(session, user) -> Item:
    item = Item(
        user_id=user.id,
        title="Bloom filters",
        source_type=SourceType.url,
        source="https://b",
        content=[{"page": None, "text": TEXT}],
    )
    session.add(item)
    session.commit()
    return item


def _note_chunks(session, item_id):
    return session.query(Chunk).filter_by(item_id=item_id, kind="note").all()


def test_highlight_quotes_the_selected_text(client, session, user):
    item = _item(session, user)
    start = TEXT.index("never")
    resp = client.post(
        f"/items/{item.id}/highlights",
        json={"start_char": start, "end_char": start + len("never give false negatives")},
    )
    assert resp.status_code == 201
    assert resp.json()["quote"] == "never give false negatives"
    assert [h["quote"] for h in client.get(f"/items/{item.id}/highlights").json()] == [
        "never give false negatives"
    ]
    assert client.get("/highlights").json()[0]["item_title"] == "Bloom filters"
    assert _note_chunks(session, item.id) == []  # a highlight without a note adds nothing new


def test_notes_become_searchable_and_are_cited_as_yours(
    client, session, user, fake_llm, monkeypatch
):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "min_similarity", 0.2)  # tuned for bge, not the fake
    item = _item(session, user)
    h = client.post(
        f"/items/{item.id}/highlights",
        json={"start_char": 0, "end_char": 13, "note": "remember this for the exam"},
    ).json()
    client.put(f"/items/{item.id}/note", json={"note": "Cuckoo filters support deletion too."})
    texts = " ".join(c.chunk_text for c in _note_chunks(session, item.id))
    assert "remember this for the exam" in texts and "Cuckoo filters" in texts

    fake_llm.answer = "Cuckoo filters support deletion [1]."
    body = client.post("/ask", json={"question": "which filters support deletion cuckoo"}).json()
    assert body["sources"][0]["kind"] == "note"
    assert "your own notes" in fake_llm.prompts[-1]

    client.patch(f"/highlights/{h['id']}", json={"note": ""})
    client.put(f"/items/{item.id}/note", json={"note": "  "})
    assert _note_chunks(session, item.id) == []
    assert client.get(f"/items/{item.id}").json()["note"] is None


def test_deleting_a_highlight(client, session, user):
    item = _item(session, user)
    h = client.post(
        f"/items/{item.id}/highlights", json={"start_char": 0, "end_char": 6, "note": "n"}
    ).json()
    assert client.delete(f"/highlights/{h['id']}").status_code == 204
    assert client.get(f"/items/{item.id}/highlights").json() == []
    assert _note_chunks(session, item.id) == []


def test_bad_ranges_and_other_peoples_items_are_refused(client, anon_client, session, user):
    item = _item(session, user)
    assert (
        client.post(
            f"/items/{item.id}/highlights", json={"start_char": 5, "end_char": 10_000}
        ).status_code
        == 422
    )
    assert (
        client.post(f"/items/{item.id}/highlights", json={"start_char": 5, "end_char": 5})
    ).status_code == 422
    anon_client.post("/auth/signup", json={"email": "x@example.com", "password": "password1"})
    assert anon_client.get(f"/items/{item.id}/highlights").status_code == 404
    assert anon_client.put(f"/items/{item.id}/note", json={"note": "hi"}).status_code == 404


def test_reprocessing_keeps_note_chunks(client, session, user):
    item = _item(session, user)
    client.put(f"/items/{item.id}/note", json={"note": "My own summary of Bloom filters."})

    class Stub:
        def extract(self, item):
            return ExtractedDoc(title="Bloom filters", pages=[PageText(None, TEXT)])

    session.expire_all()
    item = session.get(Item, item.id)
    process_item(session, item, embedder=HashingEmbedder(), llm=None, source=Stub())
    session.commit()
    assert len(_note_chunks(session, item.id)) == 1
    assert session.query(Chunk).filter_by(item_id=item.id, kind="text").count() >= 1
    assert json.dumps(item.content)  # still readable
