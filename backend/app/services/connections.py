"""How saved items connect: each item's closest neighbours by topic, with the passage in the
neighbour that's closest to it, and the same links across the whole library as a graph.

Topic closeness compares items' summary embeddings (title, summary and tags; see
pipeline.embedding_text). Shared tags count a little extra. No LLM is involved.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import select, true
from sqlalchemy.orm import Session, aliased, selectinload

from app.config import get_settings
from app.models import Chunk, Item, ItemStatus

TAG_BONUS = 0.03  # per shared tag, when ranking connections
SHARED_TAG_FLOOR = 0.5  # sharing a tag connects items down to this similarity
PASSAGE_FLOOR = 0.66  # a passage further than this from the topic isn't worth showing
GRAPH_NEIGHBOURS = 4


@dataclass
class Passage:
    chunk_id: int
    text: str
    page: int | None
    start_char: int | None
    end_char: int | None


@dataclass
class Connection:
    item: Item
    similarity: float
    shared_tags: list[str]
    passage: Passage | None


def _linkable(model):
    return (
        model.summary_embedding.is_not(None),
        model.status == ItemStatus.ready,
        model.archived.is_(False),
    )


def connections(session: Session, item: Item, limit: int = 6) -> list[Connection]:
    """The items closest in topic to `item`, best first."""
    if item.summary_embedding is None:
        return []
    threshold = get_settings().connection_min_similarity
    similarity = (1 - Item.summary_embedding.cosine_distance(item.summary_embedding)).label("s")
    rows = session.execute(
        select(Item, similarity)
        .options(selectinload(Item.tags))
        .where(Item.user_id == item.user_id, Item.id != item.id, *_linkable(Item))
        .order_by(similarity.desc())
        .limit(limit * 3)
    ).all()
    mine = {t.name for t in item.tags}
    found = []
    for other, score in rows:
        shared = sorted(mine & {t.name for t in other.tags})
        if score >= threshold or (shared and score >= SHARED_TAG_FLOOR):
            found.append(Connection(other, float(score), shared, None))
    found.sort(key=lambda c: -(c.similarity + TAG_BONUS * len(c.shared_tags)))
    found = found[:limit]
    for c in found:
        c.passage = _closest_passage(session, c.item.id, item.summary_embedding)
    return found


def _closest_passage(session: Session, item_id: int, vector) -> Passage | None:
    """The passage in item `item_id` that's closest to `vector` (the other item's topic)."""
    distance = Chunk.embedding.cosine_distance(vector)
    row = session.execute(
        select(Chunk, distance)
        .where(Chunk.item_id == item_id, Chunk.kind == "text", Chunk.embedding.is_not(None))
        .order_by(distance)
        .limit(1)
    ).first()
    if row is None or 1 - row[1] < PASSAGE_FLOOR:
        return None
    chunk = row[0]
    text = " ".join(chunk.chunk_text.split())
    return Passage(
        chunk.id,
        text[:280] + ("…" if len(text) > 280 else ""),
        chunk.page,
        chunk.start_char,
        chunk.end_char,
    )


def graph(session: Session, user_id: int) -> tuple[list[Item], list[tuple[int, int, float]]]:
    """Every linkable item, and links between each item and its few closest neighbours."""
    items = list(
        session.scalars(
            select(Item)
            .options(selectinload(Item.tags))
            .where(Item.user_id == user_id, *_linkable(Item))
            .order_by(Item.created_at)
        )
    )
    other = aliased(Item)
    distance = other.summary_embedding.cosine_distance(Item.summary_embedding).label("d")
    nearest = (
        select(other.id.label("id"), distance)
        .where(other.user_id == user_id, other.id != Item.id, *_linkable(other))
        .order_by(distance)
        .limit(GRAPH_NEIGHBOURS)
        .lateral()
    )
    rows = session.execute(
        select(Item.id, nearest.c.id, nearest.c.d)
        .join(nearest, true())
        .where(Item.user_id == user_id, *_linkable(Item))
    ).all()
    threshold = get_settings().connection_min_similarity
    tags = {i.id: {t.name for t in i.tags} for i in items}
    edges: dict[tuple[int, int], float] = {}
    for a, b, d in rows:
        similarity = 1 - d
        if similarity >= threshold or (tags[a] & tags[b] and similarity >= SHARED_TAG_FLOOR):
            edges[(min(a, b), max(a, b))] = round(float(similarity), 3)
    return items, [(a, b, s) for (a, b), s in edges.items()]


@dataclass
class Cluster:
    id: int
    item_ids: list[int]
    label: str | None  # the tag most of its items share, if any


def clusters(items: list[Item], edges: list[tuple[int, int, float]]) -> list[Cluster]:
    """Groups of items on one topic: label propagation over the links, weighted by
    similarity (each item takes the group its neighbours pull hardest towards). Deterministic;
    items with no links stay out of every group. Groups are named after the tag shared by the
    most members, when at least two share one."""
    neighbours: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for a, b, s in edges:
        neighbours[a].append((b, s))
        neighbours[b].append((a, s))
    group = {i.id: i.id for i in items}
    for _ in range(20):
        changed = False
        for node in sorted(neighbours):
            pull: dict[int, float] = defaultdict(float)
            for other, s in neighbours[node]:
                pull[group[other]] += s
            pull[group[node]] += 0.0  # staying put competes on equal terms
            best = min(pull, key=lambda g: (-pull[g], g))
            if pull[best] > pull[group[node]] + 1e-9 and best != group[node]:
                group[node], changed = best, True
        if not changed:
            break
    members: dict[int, list[int]] = defaultdict(list)
    for item_id, g in group.items():
        if item_id in neighbours:
            members[g].append(item_id)
    tags = {i.id: [t.name for t in i.tags] for i in items}
    found = []
    for n, ids in enumerate(sorted(members.values(), key=lambda m: (-len(m), min(m))), start=1):
        if len(ids) < 2:
            continue
        counts = Counter(t for i in ids for t in tags[i])
        top = min(counts.items(), key=lambda kv: (-kv[1], kv[0]), default=None)
        found.append(Cluster(n, sorted(ids), top[0] if top and top[1] >= 2 else None))
    return found
