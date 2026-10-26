# The Recall API (and, with RUN_WORKER_IN_API=true, the background worker in the same process).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    MODEL_CACHE_DIR=/app/models \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv
WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

# Bake the embedding model into the image: a cold start then loads it from disk instead of
# downloading 130 MB.
RUN python -c "from app.config import get_settings as s; from app.services.embeddings import FastEmbedder; FastEmbedder(s().embedding_model, s().model_cache_dir)"

EXPOSE 8000
# Migrations run on start, so a new release updates the database before serving.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
