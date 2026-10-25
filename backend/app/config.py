from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings, read from environment variables or a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://recall:recall@localhost:5432/recall"
    gemini_api_key: str | None = None
    # Flash-Lite answers in about a second, which keeps questions inside NFR-2's 5 to 10 s.
    gemini_model: str = "gemini-3.5-flash-lite"
    # Tried in order when the main model is rate-limited or overloaded.
    gemini_fallback_models: list[str] = ["gemini-3.1-flash-lite"]
    upload_dir: str = "data/uploads"
    max_upload_mb: int = 25
    cors_origins: list[str] = ["http://localhost:3000"]
    embedding_dim: int = 384
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    model_cache_dir: str = "data/models"

    # Fetching web articles
    fetch_timeout_s: float = 20.0
    max_fetch_mb: int = 15
    fetch_contact: str | None = None  # put in the User-Agent; some sites require one
    allow_private_urls: bool = False  # only for local testing; blocks SSRF in a hosted demo

    # Characters of a document the LLM sees when writing its summaries (sampled from start,
    # middle and end when longer). The one exception to "only short passages go to the LLM".
    summary_input_chars: int = 40_000

    # Chunking, in approximate tokens (see app/services/text.py)
    chunk_tokens: int = 400
    chunk_overlap: int = 60

    # Retrieval and answering
    candidate_k: int = 20  # taken from each of vector and keyword search before fusion
    answer_k: int = 6  # passages sent to the LLM
    # Below this closest-passage cosine similarity, reply "not found" without calling the LLM.
    # Tuned in eval/results.md: off-topic questions score under it, real ones above.
    min_similarity: float = 0.58
    # "hybrid", "vector", "keyword", or "rerank" (hybrid, then a cross-encoder re-scores the
    # top rerank_pool passages). See eval/results.md for how they compare.
    search_mode: str = "hybrid"
    rerank_model: str = "jinaai/jina-reranker-v1-turbo-en"
    rerank_pool: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
