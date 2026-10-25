# Recall

Save PDFs and web articles in one place, then ask questions in plain English and get answers built
only from your own library, with a citation to the exact passage.

> Status: milestones 1 to 4 built. PDFs and links are extracted, chunked, embedded locally,
> summarised and tagged in the background; questions get streamed answers with clickable
> citations, or "not found in your library". The evaluation harness (milestone 5) is next.

## How it works

- **Save:** `POST /items` stores a PDF or URL and queues a background job.
- **Process:** a worker claims jobs from Postgres (`FOR UPDATE SKIP LOCKED`), extracts text,
  chunks it, embeds each chunk locally, and asks the LLM for a summary and tags.
- **Ask:** hybrid search (pgvector + Postgres full-text) finds the best passages; the LLM answers
  from those passages only, or says "not found in your library".
- **Browse:** tag filters are a plain SQL lookup, no LLM involved.

| Layer | Tech |
| --- | --- |
| Web | Next.js 15, TypeScript, Tailwind v4, shadcn/ui, TanStack Query |
| API | FastAPI, SQLAlchemy 2, Alembic, answers streamed over Server-Sent Events |
| Data | PostgreSQL + pgvector (HNSW) + built-in full-text search, merged with reciprocal rank fusion |
| Jobs | A Postgres `jobs` table with `FOR UPDATE SKIP LOCKED`, retries with backoff, no Redis |
| Embeddings | bge-small-en-v1.5 via fastembed (ONNX), run locally |
| LLM | Gemini Flash-Lite with fallback models, behind one swappable interface |

## Run it locally

Recall runs as three processes: the **API** (FastAPI), the **worker** that reads saved items in
the background, and the **web app** (Next.js). All three talk to one Postgres database.

### 1. Install the tools

- [uv](https://docs.astral.sh/uv/) for Python (it installs Python 3.12 for you)
- Node.js 22 or newer
- PostgreSQL with the [pgvector](https://github.com/pgvector/pgvector) extension (step 2)
- A free Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)

On macOS with Homebrew:

```bash
brew install uv node postgresql@17 pgvector
```

### 2. Start Postgres

Pick one.

**Homebrew (macOS):**

```bash
brew services start postgresql@17
/opt/homebrew/opt/postgresql@17/bin/psql postgres -c "CREATE ROLE recall LOGIN SUPERUSER PASSWORD 'recall'"
/opt/homebrew/opt/postgresql@17/bin/createdb -O recall recall
/opt/homebrew/opt/postgresql@17/bin/createdb -O recall recall_test   # only needed for tests
```

**Docker:**

```bash
docker compose up -d
docker compose exec db createdb -U recall recall_test                 # only needed for tests
```

Either way, the database URL is
`postgresql+psycopg://recall:recall@localhost:5432/recall`.

**Neon (hosted, free):** create a project at [neon.tech](https://neon.tech) and copy its
connection string, changing the `postgresql://` prefix to `postgresql+psycopg://`.

### 3. Configure the backend

```bash
cd backend
cp ../.env.example .env
```

Open `backend/.env` and set:

| Setting | Value |
| --- | --- |
| `DATABASE_URL` | the URL from step 2 |
| `GEMINI_API_KEY` | your key from Google AI Studio |
| `FETCH_CONTACT` | optional: your repo URL or email. Wikipedia blocks article fetches without one |

`.env` is git-ignored. Never commit it.

### 4. Set up and start the API

```bash
cd backend
uv sync                                  # installs Python 3.12 and the dependencies
uv run alembic upgrade head              # creates the tables
uv run uvicorn app.main:app --reload     # API on http://localhost:8000 (docs at /docs)
```

### 5. Start the worker (second terminal)

```bash
cd backend
uv run python -m app.worker
```

The first start downloads the embedding model (about 130 MB) into `backend/data/models`. Later
starts take a few seconds. Leave it running: it reads every PDF and link you save.

### 6. Start the web app (third terminal)

```bash
cd frontend
npm install
npm run dev                              # http://localhost:3000
```

The web app expects the API at `http://localhost:8000`. To point it somewhere else, put
`NEXT_PUBLIC_API_URL=...` in `frontend/.env.local`.

### 7. Try it

1. Open http://localhost:3000.
2. Upload a PDF, or paste a link such as `https://arxiv.org/pdf/1706.03762`.
3. Its status goes from *Queued* to *Reading* to *Ready* in a few seconds, with a summary and tags.
4. Go to **Ask** and ask something the document answers. The answer streams in with numbered
   citations; click one to see the exact passage, and for a PDF, to open it at that page.
5. Ask something it doesn't cover. Recall replies "Not found in your library" instead of guessing.

### Troubleshooting

- **"Can't reach the Recall API"**: the API from step 4 isn't running, or it's on another port.
- **An item stays *Queued***: the worker from step 5 isn't running.
- **An item *Failed***: the message on the item says why. Scanned PDFs (images with no text)
  and pages behind a login can't be read. Fix the cause, then press *Try again*.
- **"GEMINI_API_KEY is not set"**: add the key to `backend/.env`, restart the API and the
  worker, then retry the item.
- **Gemini errors about the model**: models get retired. Set `GEMINI_MODEL` in `backend/.env`
  to a current one from [the model list](https://ai.google.dev/gemini-api/docs/models).

## Tests

```bash
cd backend
uv run pytest                            # 78 tests, against the recall_test database
uv run ruff check . && uv run ruff format --check .

cd ../frontend
npm run lint && npm run build
```

Tests run against a real Postgres. They use `recall_test` by default (set `DATABASE_URL` to
change it) and reset its tables, so never point them at your real library. They use a fake LLM and
a fake embedder, so they need no API key or model download.
