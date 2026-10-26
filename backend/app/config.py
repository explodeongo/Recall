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
    file_store: str = "local"  # "local" (UPLOAD_DIR) or "database" (survives disk wipes)
    max_upload_mb: int = 25
    cors_origins: list[str] = ["http://localhost:3000"]
    # Where the API and the web app are reached from outside: links handed to AI assistants
    # over MCP point at the web app, and assistants connect to the API's /mcp.
    public_api_url: str = "http://localhost:8000"
    web_url: str = "http://localhost:3000"
    cookie_secure: bool = False  # set true when served over https
    ask_per_minute: int = 20  # questions per person per minute, to protect the LLM quota

    # For a public deployment.
    run_worker_in_api: bool = False  # run the job loop inside the API (no separate worker)
    signup_code: str | None = None  # if set, signing up needs this invite code
    daily_items: int = 200  # things one person can save per day
    daily_questions: int = 300  # questions (Ask and chats) one person can ask per day
    daily_quizzes: int = 50  # "quiz me" runs per person per day
    embedding_dim: int = 384
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    model_cache_dir: str = "data/models"

    # Fetching web articles
    fetch_timeout_s: float = 20.0
    max_fetch_mb: int = 15
    fetch_contact: str | None = None  # put in the User-Agent; some sites require one
    tavily_api_key: str | None = None  # optional: reliable web search (free plan available)
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
    # Library search adds documents whose topic (summary embedding) is at least this close to
    # the query, as "related". Measured on real queries: "my CV" vs a résumé 0.60, unrelated
    # documents under 0.55.
    related_min_similarity: float = 0.57
    rerank_model: str = "jinaai/jina-reranker-v1-turbo-en"
    rerank_pool: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
