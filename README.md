# Recall

Save PDFs and web articles in one place, then ask questions in plain English and get answers built
only from your own library, with a citation to the exact passage.

> Status: milestone 1 (skeleton). Schema, job queue, item and tag endpoints, and the Library page
> work. Text extraction, embeddings and question answering are next.

## How it works

- **Save:** `POST /items` stores a PDF or URL and queues a background job.
- **Process:** a worker claims jobs from Postgres (`FOR UPDATE SKIP LOCKED`), extracts text,
  chunks it, embeds each chunk locally, and asks the LLM for a summary and tags.
- **Ask:** hybrid search (pgvector + Postgres full-text) finds the best passages; the LLM answers
  from those passages only, or says "not found in your library".
- **Browse:** tag filters are a plain SQL lookup, no LLM involved.

| Layer | Tech |
| --- | --- |
| Web | Next.js, TypeScript, Tailwind |
| API | FastAPI, SQLAlchemy 2, Alembic |
| Data | PostgreSQL 16 + pgvector (HNSW) + full-text search |
| Embeddings | bge-small-en-v1.5, run locally |
| LLM | Gemini, behind one swappable interface |

## Run it locally

You need Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22, and a Postgres database with
pgvector. A free [Neon](https://neon.tech) database works, and so does `docker compose up -d`.

```bash
# backend
cd backend
cp ../.env.example .env        # fill in DATABASE_URL and GEMINI_API_KEY
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload     # API on :8000, docs at /docs
uv run python -m app.worker              # in a second terminal

# frontend
cd frontend
npm install
npm run dev                              # http://localhost:3000
```

## Tests

```bash
cd backend && uv run pytest
```

Tests run against a real Postgres. Point `DATABASE_URL` at a throwaway database, since the tests
reset its tables.
