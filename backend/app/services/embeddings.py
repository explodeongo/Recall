"""Local embeddings (NFR-6): bge-small-en-v1.5 through fastembed's ONNX runtime, no PyTorch.

The model is loaded once per process and reused. Tests swap in `HashingEmbedder`, so CI never
downloads a model.
"""

import hashlib
import math
import re
from functools import lru_cache
from typing import Protocol

from app.config import get_settings

# bge models are trained with this instruction in front of search queries, and not passages.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


# Passages embedded at a time. Larger batches are no faster, but ONNX Runtime keeps the memory
# of the largest batch it has seen: 32 long passages took 840 MB, past a small server's limit;
# 2 take about 30 MB.
BATCH = 2


class FastEmbedder:
    def __init__(self, model_name: str, cache_dir: str, threads: int | None = None):
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir, threads=threads)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [vec.tolist() for vec in self._model.embed(texts, batch_size=BATCH)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.embed([QUERY_PREFIX + text]))).tolist()


class HashingEmbedder:
    """A deterministic stand-in for tests: a bag of hashed words, L2-normalised.

    Texts that share words get similar vectors, which is enough to test search end to end.
    """

    def __init__(self, dim: int = 384):
        self.dim = dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for word in re.findall(r"\w+", text.lower()):
            digest = hashlib.blake2b(word.encode(), digest_size=4).digest()
            vec[int.from_bytes(digest, "big") % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


@lru_cache
def get_embedder() -> Embedder:
    settings = get_settings()
    return FastEmbedder(settings.embedding_model, settings.model_cache_dir, settings.model_threads)
