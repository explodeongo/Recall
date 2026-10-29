"""Optional second-stage ranking with a local cross-encoder.

Hybrid search scores the question and each passage separately. A cross-encoder reads the two
together, which is slower but much better at telling which passage actually answers the
question, so it re-scores only the top candidates.
"""

from functools import lru_cache
from typing import Protocol

from app.config import get_settings
from app.services.embeddings import BATCH


class Reranker(Protocol):
    def score(self, query: str, passages: list[str]) -> list[float]: ...


class CrossEncoderReranker:
    def __init__(self, model_name: str, cache_dir: str, threads: int | None = None):
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self._model = TextCrossEncoder(model_name=model_name, cache_dir=cache_dir, threads=threads)

    def score(self, query: str, passages: list[str]) -> list[float]:
        return [float(s) for s in self._model.rerank(query, passages, batch_size=BATCH)]


@lru_cache
def get_reranker() -> Reranker:
    settings = get_settings()
    return CrossEncoderReranker(
        settings.rerank_model, settings.model_cache_dir, settings.model_threads
    )
