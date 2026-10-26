"""Searching the library for documents (the Library's search box and the ⌘K box).

Each word of the query is matched on its own, anywhere in a document: its title, tags,
summary, the reader's note, or its full text (Postgres full-text search, with prefixes, so
results keep up while you type). Documents matching more of the words rank higher, title
matches first. Each result carries the passage where the words occur, with them marked.

Documents that match none of the words but whose topic (title, summary and tags, embedded) is
close to the query are added after, marked "related", so "my CV" still finds a résumé.
"""

import re
from dataclasses import dataclass

from sqlalchemy import Integer, case, cast, func, literal, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models import Chunk, Item, Tag
from app.services.embeddings import Embedder
from app.services.tags import has_tags

MAX_WORDS = 8
MAX_RESULTS = 50
MARK_START, MARK_END = "⁣[[", "]]⁣"  # unlikely in real text; the UI turns them into marks


@dataclass
class Match:
    kind: str  # "text": the words occur in this passage; "related": similar in meaning
    snippet: str
    page: int | None
    chunk_id: int | None
    start_char: int | None
    end_char: int | None


def query_words(q: str) -> list[str]:
    words = list(dict.fromkeys(w.lower() for w in re.findall(r"\w+", q)))
    keep = [w for w in words if len(w) > 1] or words
    return keep[:MAX_WORDS]


def _like(word: str) -> str:
    return "%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search_items(
    session: Session,
    user_id: int,
    q: str,
    *,
    tags: list[str] | None = None,
    match: str = "all",
    embedder: Embedder | None = None,
    limit: int = MAX_RESULTS,
) -> list[Item]:
    """Matching items, best first, each with a `.match` attribute (a Match, or None when only
    the title or metadata matched)."""
    words = query_words(q)
    if not words:
        return []

    hits, title_hits = [], []
    for word in words:
        like = _like(word)
        prefix = func.to_tsquery("english", f"{word}:*")
        in_title = Item.title.ilike(like, escape="\\")
        anywhere = or_(
            in_title,
            Item.summary.ilike(like, escape="\\"),
            Item.note.ilike(like, escape="\\"),
            Item.tags.any(Tag.name.ilike(like, escape="\\")),
            select(Chunk.id).where(Chunk.item_id == Item.id, Chunk.tsv.op("@@")(prefix)).exists(),
        )
        hits.append(case((anywhere, 1), else_=0))
        title_hits.append(case((in_title, 1), else_=0))
    matched = sum(hits[1:], hits[0])
    in_titles = sum(title_hits[1:], title_hits[0])
    # Ties: the whole query as a phrase beats scattered words; then the document whose topic
    # is closest to the query (so a résumé beats a paper that happens to say "application");
    # then words close together in the text (cover density) beat words far apart.
    phrase = or_(
        Item.title.ilike(_like(" ".join(q.split())), escape="\\"),
        select(Chunk.id)
        .where(Chunk.item_id == Item.id, Chunk.tsv.op("@@")(func.phraseto_tsquery("english", q)))
        .exists(),
    )
    any_word = func.to_tsquery("english", " | ".join(f"{w}:*" for w in words))
    closeness = (
        select(func.max(func.ts_rank_cd(Chunk.tsv, any_word)))
        .where(Chunk.item_id == Item.id)
        .scalar_subquery()
    )

    topic = (
        (1 - Item.summary_embedding.cosine_distance(embedder.embed_query(q)))
        if embedder is not None
        else literal(0.0)
    )

    stmt = (
        select(Item, cast(matched, Integer).label("matched"))
        .options(selectinload(Item.tags))
        .where(Item.user_id == user_id, matched >= 1)
        .order_by(
            matched.desc(),
            case((phrase, 1), else_=0).desc(),
            in_titles.desc(),
            func.coalesce(topic, 0).desc(),
            func.coalesce(closeness, 0).desc(),
            Item.created_at.desc(),
        )
        .limit(limit)
    )
    stmt = stmt.where(has_tags(tags or [], match))
    items = [item for item, _ in session.execute(stmt).all()]
    snippets = _snippets(session, [i.id for i in items], words)
    for item in items:
        item.match = snippets.get(item.id)

    if embedder is not None and len(q.strip()) >= 3 and len(items) < limit:
        items += _related(
            session,
            embedder,
            user_id,
            q,
            has_tags(tags or [], match),
            {i.id for i in items},
            limit - len(items),
        )
    return items


def _snippets(session: Session, item_ids: list[int], words: list[str]) -> dict[int, Match]:
    """For each item, the passage that matches the words best, with them marked."""
    if not item_ids:
        return {}
    query = func.to_tsquery("english", " | ".join(f"{w}:*" for w in words))
    rank = func.ts_rank_cd(Chunk.tsv, query)
    headline = func.ts_headline(
        "english",
        Chunk.chunk_text,
        query,
        literal(
            f"StartSel={MARK_START}, StopSel={MARK_END}, MaxWords=32, MinWords=14, "
            "MaxFragments=1, ShortWord=2"
        ),
    )
    rows = session.execute(
        select(Chunk.item_id, Chunk.id, Chunk.page, Chunk.start_char, Chunk.end_char, headline)
        .where(Chunk.item_id.in_(item_ids), Chunk.tsv.op("@@")(query))
        .ext(distinct_on(Chunk.item_id))
        .order_by(Chunk.item_id, rank.desc())
    ).all()
    return {
        r[0]: Match("text", _tidy(r[5]), r[2], r[1], r[3], r[4]) for r in rows if MARK_START in r[5]
    }


def _related(
    session, embedder, user_id, q, tag_filter, exclude: set[int], limit: int
) -> list[Item]:
    """Items whose topic is close to the query, compared on their summary embeddings."""
    threshold = get_settings().related_min_similarity
    vector = embedder.embed_query(q)
    similarity = (1 - Item.summary_embedding.cosine_distance(vector)).label("similarity")
    stmt = (
        select(Item, similarity)
        .options(selectinload(Item.tags))
        .where(
            Item.user_id == user_id,
            Item.summary_embedding.is_not(None),
            Item.id.not_in(exclude or {-1}),
        )
        .order_by(similarity.desc())
        .where(tag_filter)
        .limit(limit)
    )
    related = []
    for item, score in session.execute(stmt).all():
        if score < threshold:
            break
        summary = " ".join((item.summary or "").split())
        item.match = Match(
            "related", summary[:220] + ("…" if len(summary) > 220 else ""), None, None, None, None
        )
        related.append(item)
    return related


def _tidy(snippet: str) -> str:
    return " ".join(snippet.split())
