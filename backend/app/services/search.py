"""Hybrid retrieval: pgvector cosine search and Postgres full-text search, merged with
reciprocal rank fusion (RRF).

Vector search finds passages that mean the same thing in other words; keyword search finds
exact names, numbers and jargon that embeddings blur. RRF merges the two ranked lists using
only ranks, so the two very different score scales never have to be compared.
"""

from dataclasses import dataclass, replace
from enum import StrEnum

from sqlalchemy import Text, cast, func, select, text
from sqlalchemy.orm import Session

from app.models import Chunk, Item, SourceType
from app.services.embeddings import Embedder
from app.services.rerank import Reranker

RRF_K = 60


class SearchMode(StrEnum):
    hybrid = "hybrid"
    vector = "vector"
    keyword = "keyword"
    rerank = "rerank"  # hybrid, then a cross-encoder re-scores the top candidates


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
    # Position in the item's full text. Unlike chunk ids, it survives reprocessing, so saved
    # answers can still point at the passage.
    start_char: int | None = None
    end_char: int | None = None


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
    reranker: Reranker | None = None,
    rerank_pool: int = 20,
    item_ids: list[int] | None = None,
    user_id: int | None = None,
) -> SearchResult:
    """`user_id` limits the search to one person's library and `item_ids` to particular items
    (a chat about one document). Without either, the whole database is searched (evaluation)."""
    scope = _Scope(item_ids, user_id)
    vector_hits = _vector_search(session, embedder.embed_query(query), candidate_k, scope)
    best = vector_hits[0][1] if vector_hits else None

    rankings: list[list[int]] = []
    if mode in (SearchMode.hybrid, SearchMode.vector, SearchMode.rerank):
        rankings.append([chunk_id for chunk_id, _ in vector_hits])
    if mode in (SearchMode.hybrid, SearchMode.keyword, SearchMode.rerank):
        rankings.append(_keyword_search(session, query, candidate_k, scope))
    fused = rrf(rankings)

    if mode != SearchMode.rerank:
        return SearchResult(passages=_load(session, fused[:k]), best_similarity=best)
    if reranker is None:
        raise ValueError("rerank mode needs a reranker")
    pool = _load(session, fused[:rerank_pool])
    scores = reranker.score(query, [f"{p.title}\n\n{p.text}" for p in pool])
    ranked = sorted(zip(scores, pool, strict=True), key=lambda pair: -pair[0])[:k]
    passages = [replace(p, score=score) for score, p in ranked]
    return SearchResult(passages=passages, best_similarity=best)


def rrf(rankings: list[list[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Reciprocal rank fusion: score(d) = sum over lists of 1 / (k + rank of d in that list)."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


@dataclass(frozen=True)
class _Scope:
    item_ids: list[int] | None = None
    user_id: int | None = None

    def apply(self, stmt):
        if self.item_ids is not None:
            stmt = stmt.where(Chunk.item_id.in_(self.item_ids))
        if self.user_id is not None:
            stmt = stmt.join(Item, Item.id == Chunk.item_id).where(Item.user_id == self.user_id)
        return stmt

    @property
    def filtered(self) -> bool:
        return self.item_ids is not None or self.user_id is not None


_EVERYTHING = _Scope()


def _vector_search(
    session: Session, vector: list[float], limit: int, scope: _Scope = _EVERYTHING
) -> list[tuple[int, float]]:
    if scope.filtered:
        # With a filter, the HNSW index would stop after its first candidates and could return
        # too few rows; iterative scan keeps going until enough rows pass the filter.
        session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    distance = Chunk.embedding.cosine_distance(vector)
    stmt = select(Chunk.id, (1 - distance).label("similarity")).where(Chunk.embedding.is_not(None))
    rows = session.execute(scope.apply(stmt).order_by(distance).limit(limit)).all()
    # relaxed_order can return near-ties slightly out of order; put them back.
    return sorted(((row.id, float(row.similarity)) for row in rows), key=lambda r: -r[1])


def _keyword_search(
    session: Session, query: str, limit: int, scope: _Scope = _EVERYTHING
) -> list[int]:
    # plainto_tsquery stems the words and drops stop words but ANDs them together, which
    # misses most passages for a natural question. Swapping & for | ORs them instead, and
    # ts_rank_cd then favours chunks that contain more of the words close together.
    anded = cast(func.plainto_tsquery("english", query), Text)
    tsquery = func.to_tsquery("english", func.replace(anded, "&", "|"))
    rank = func.ts_rank_cd(Chunk.tsv, tsquery)
    stmt = scope.apply(select(Chunk.id).where(Chunk.tsv.op("@@")(tsquery)))
    return list(session.scalars(stmt.order_by(rank.desc()).limit(limit)))


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
                start_char=chunk.start_char,
                end_char=chunk.end_char,
            )
        )
    return passages
