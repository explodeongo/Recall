from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings, read from environment variables or a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://recall:recall@localhost:5432/recall"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    upload_dir: str = "data/uploads"
    max_upload_mb: int = 25
    cors_origins: list[str] = ["http://localhost:3000"]
    embedding_dim: int = 384


@lru_cache
def get_settings() -> Settings:
    return Settings()
