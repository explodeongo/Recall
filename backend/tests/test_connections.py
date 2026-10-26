import math

from app.models import Chunk, Item, SourceType, Tag


def _vec(**weights):
    """A unit vector with the given weights on axes a, b, c, d (the rest zero)."""
    v = [0.0] * 384
    for axis, w in weights.items():
        v["abcd".index(axis)] = w
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v]


def _library(session, user):
    sleep = Tag(name="sleep", user_id=user.id)
    common = {"user_id": user.id, "source_type": SourceType.url, "status": "ready"}
    a = Item(
        title="Melatonin", source="https://a", summary_embedding=_vec(a=1), tags=[sleep], **common
    )
    b = Item(
        title="Circadian rhythm", source="https://b", summary_embedding=_vec(a=0.8, b=0.6), **common
    )
    c = Item(title="Tax law", source="https://c", summary_embedding=_vec(c=1), **common)
    # Only loosely related, but it shares a tag, which is enough.
    d = Item(
        title="Sleep journal",
        source="https://d",
        summary_embedding=_vec(a=0.52, d=0.85),
        tags=[sleep],
        **common,
    )
    archived = Item(
        title="Old", source="https://e", summary_embedding=_vec(a=1), archived=True, **common
    )
    session.add_all([a, b, c, d, archived])
    session.flush()
    session.add_all(
        [
            Chunk(
                item_id=b.id,
                chunk_index=0,
                chunk_text="Light resets the clock.",
                embedding=_vec(b=1),
            ),
            Chunk(
                item_id=b.id,
                chunk_index=1,
                chunk_text="Melatonin peaks at night.",
                embedding=_vec(a=1),
                page=2,
            ),
        ]
    )
    session.commit()
    return a, b, c, d


def test_connections_rank_by_topic_and_point_to_the_closest_passage(client, session, user):
    a, b, c, d = _library(session, user)
    found = client.get(f"/items/{a.id}/connections").json()
    assert [f["item"]["title"] for f in found] == ["Circadian rhythm", "Sleep journal"]
    assert found[0]["passage"]["text"] == "Melatonin peaks at night."
    assert found[0]["passage"]["page"] == 2
    assert found[1]["shared_tags"] == ["sleep"]
    assert client.get(f"/items/{c.id}/connections").json() == []
    assert client.get("/items/999/connections").status_code == 404


def test_graph_links_related_items_once(client, session, user):
    a, b, c, d = _library(session, user)
    graph = client.get("/graph").json()
    assert {n["title"] for n in graph["nodes"]} == {
        "Melatonin",
        "Circadian rhythm",
        "Tax law",
        "Sleep journal",
    }
    pairs = {frozenset((e["source"], e["target"])) for e in graph["edges"]}
    assert pairs == {frozenset((a.id, b.id)), frozenset((a.id, d.id))}
    tags = {n["title"]: n["tags"] for n in graph["nodes"]}
    assert tags["Melatonin"][0]["name"] == "sleep" and tags["Melatonin"][0]["color"].startswith("#")


def test_clusters_group_linked_items_and_take_a_shared_tag_as_name():
    from types import SimpleNamespace

    from app.services.connections import clusters

    def item(i, *tags):
        return SimpleNamespace(id=i, tags=[SimpleNamespace(name=t) for t in tags])

    items = [
        item(1, "sleep"),
        item(2, "sleep"),
        item(3, "sleep", "health"),
        item(4, "tax"),
        item(5, "tax"),
        item(6),
    ]
    # Two tight groups joined by one weak link, and an item linked to nothing.
    edges = [(1, 2, 0.8), (2, 3, 0.8), (1, 3, 0.75), (4, 5, 0.8), (3, 4, 0.52)]
    found = clusters(items, edges)
    assert [(c.item_ids, c.label) for c in found] == [([1, 2, 3], "sleep"), ([4, 5], "tax")]


def test_graph_reports_clusters(client, session, user):
    a, b, c, d = _library(session, user)
    graph = client.get("/graph").json()
    by_title = {n["title"]: n["cluster"] for n in graph["nodes"]}
    assert by_title["Tax law"] is None
    assert by_title["Melatonin"] == by_title["Circadian rhythm"] == by_title["Sleep journal"]
    assert graph["clusters"][0]["label"] == "sleep" and graph["clusters"][0]["color"]


def test_reference_lists_are_not_shown_as_the_linking_passage():
    from app.services.connections import _looks_like_references

    assert _looks_like_references(
        "Robertson, S. (1994). Okapi at TREC-3. doi:10.1016/0306-4573(88)90021-0. Retrieved 2 May"
    )
    assert _looks_like_references("Information Processing & Management. 24 (5): 513-523. doi:10.1")
    assert not _looks_like_references(
        "BM25 ranks documents by how often the query terms appear, scaled by document length."
    )
    assert not _looks_like_references("The transformer was introduced in 2017 by Vaswani et al.")
