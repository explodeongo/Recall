"""Hybrid retrieval: pgvector cosine search and Postgres full-text search, merged with
reciprocal rank fusion (RRF).

Vector search finds passages that mean the same thing in other words; keyword search finds
exact names, numbers and jargon that embeddings blur. RRF merges the two ranked lists using
only ranks, so the two very different score scales never have to be compared.
"""

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import Text, cast, func, select
from sqlalchemy.orm import Session

from app.models import Chunk, Item, SourceType
from app.services.embeddings import Embedder

RRF_K = 60


class SearchMode(StrEnum):
    hybrid = "hybrid"
    vector = "vector"
    keyword = "keyword"


@dataclass(frozen=True)
class Passage:
    chunk_id: int
    item_id: int
    title: str
    source_type: SourceType
    source: str
    page: int | None
    text: str
    score: float


@dataclass(frozen=True)
class SearchResult:
    passages: list[Passage]
    # Cosine similarity of the closest chunk to the question; the "not found" gate uses it.
    best_similarity: float | None


def search(
    session: Session,
    embedder: Embedder,
    query: str,
    *,
    mode: SearchMode = SearchMode.hybrid,
    k: int = 6,
    candidate_k: int = 20,
) -> SearchResult:
    vector_hits = _vector_search(session, embedder.embed_query(query), candidate_k)
    best = vector_hits[0][1] if vector_hits else None

    rankings: list[list[int]] = []
    if mode in (SearchMode.hybrid, SearchMode.vector):
        rankings.append([chunk_id for chunk_id, _ in vector_hits])
    if mode in (SearchMode.hybrid, SearchMode.keyword):
        rankings.append(_keyword_search(session, query, candidate_k))

    fused = rrf(rankings)[:k]
    return SearchResult(passages=_load(session, fused), best_similarity=best)


def rrf(rankings: list[list[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Reciprocal rank fusion: score(d) = sum over lists of 1 / (k + rank of d in that list)."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


def _vector_search(session: Session, vector: list[float], limit: int) -> list[tuple[int, float]]:
    distance = Chunk.embedding.cosine_distance(vector)
    rows = session.execute(
        select(Chunk.id, (1 - distance).label("similarity"))
        .where(Chunk.embedding.is_not(None))
        .order_by(distance)
        .limit(limit)
    ).all()
    return [(row.id, float(row.similarity)) for row in rows]


def _keyword_search(session: Session, query: str, limit: int) -> list[int]:
    # plainto_tsquery stems the words and drops stop words but ANDs them together, which
    # misses most passages for a natural question. Swapping & for | ORs them instead, and
    # ts_rank_cd then favours chunks that contain more of the words close together.
    anded = cast(func.plainto_tsquery("english", query), Text)
    tsquery = func.to_tsquery("english", func.replace(anded, "&", "|"))
    rank = func.ts_rank_cd(Chunk.tsv, tsquery)
    return list(
        session.scalars(
            select(Chunk.id).where(Chunk.tsv.op("@@")(tsquery)).order_by(rank.desc()).limit(limit)
        )
    )


def _load(session: Session, fused: list[tuple[int, float]]) -> list[Passage]:
    if not fused:
        return []
    rows = session.execute(
        select(Chunk, Item)
        .join(Item, Item.id == Chunk.item_id)
        .where(Chunk.id.in_([chunk_id for chunk_id, _ in fused]))
    ).all()
    by_id = {chunk.id: (chunk, item) for chunk, item in rows}
    passages = []
    for chunk_id, score in fused:
        chunk, item = by_id[chunk_id]
        passages.append(
            Passage(
                chunk_id=chunk.id,
                item_id=item.id,
                title=item.title,
                source_type=item.source_type,
                source=item.source,
                page=chunk.page,
                text=chunk.chunk_text,
                score=score,
            )
        )
    return passages
