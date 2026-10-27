from app.models import Chunk, Item, SourceType
from app.services.links import title_terms

TEXT = (
    "Melatonin is made in the pineal gland. Bright light suppresses melatonin, and so does "
    "alcohol.\n\nThe circadian rhythm sets when melatonin rises. Okapi BM25 has nothing to do "
    "with sleep, and neither does the RNN, though an rnn of sorts is in every story."
)


def _item(session, user, title, text, concepts=(), summary=None):
    item = Item(
        user_id=user.id,
        title=title,
        source_type=SourceType.url,
        source="https://x",
        status="ready",
        content=[{"page": None, "text": text}],
        summary=text if summary is None else summary,
        details={"concepts": list(concepts)},
    )
    session.add(item)
    session.flush()
    session.add(
        Chunk(item_id=item.id, chunk_index=0, chunk_text=text, start_char=0, end_char=len(text))
    )
    return item


def test_titles_become_names_when_they_look_like_one():
    assert title_terms("Transformer (deep learning)") == ["Transformer"]
    assert title_terms("Okapi BM25") == ["Okapi BM25"]
    assert title_terms("Let's build GPT: from scratch, in code, spelled out.") == []
    assert title_terms("Sleep - Wikipedia") == ["Sleep"]


def test_terms_from_other_items_link_to_them_with_the_passage(client, session, user):
    reading = _item(session, user, "Sleep and light", TEXT, concepts=["melatonin"])
    hormone = _item(session, user, "Melatonin", "Melatonin is a hormone that regulates sleep.")
    rhythm = _item(
        session,
        user,
        "Daily clocks",
        "A circadian rhythm repeats every 24 hours.",
        ["circadian rhythm"],
    )
    _item(session, user, "Okapi BM25", "BM25 ranks documents.")
    _item(session, user, "Recurrent networks", "An RNN reads one token at a time.", ["RNN"])
    _item(session, user, "Notes", "Generic.", ["memory", "data"])  # too generic to link
    # Named in passing, not what this item is about: no link for "pineal gland".
    _item(
        session,
        user,
        "Bones",
        "The pineal gland is small, but this is about bones.",
        ["pineal gland"],
        summary="How bones grow and heal.",
    )
    session.commit()

    links = client.get(f"/items/{reading.id}/links").json()
    terms = [(link["term"], TEXT[link["start"] : link["end"]]) for link in links]
    assert terms == [
        ("Melatonin", "Melatonin"),
        ("melatonin", "melatonin"),  # two per term, then no more
        ("circadian rhythm", "circadian rhythm"),
        ("Okapi BM25", "Okapi BM25"),  # the longer name wins over a shorter one inside it
        ("RNN", "RNN"),  # but not the lowercase "rnn"
    ]
    first = links[0]["targets"][0]
    assert first["item_id"] == hormone.id and "hormone" in first["snippet"]
    assert links[2]["targets"][0]["item_id"] == rhythm.id
    assert client.get("/items/999/links").status_code == 404
