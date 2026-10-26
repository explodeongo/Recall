# Recall

Save PDFs and web articles in one place, then ask questions in plain English and get answers built
only from your own library, with a citation to the exact passage.

![CI](https://github.com/explodeongo/Recall/actions/workflows/ci.yml/badge.svg)

![Ask: an answer from the library, every claim cited](docs/screenshots/ask.jpg)

## What it does

- **Save anything:** PDFs, Word, Markdown and text files, links to articles, PDFs or YouTube
  videos (read from their captions), or a note typed straight in. Paste a list of links at
  once, save the page you're on with the "Save to Recall" bookmark button, or share to Recall
  from your phone once it's installed. Each item is read in the background and gets a
  two-line summary, a page-long summary (overview, key points, section by section) and tags.
- **Read and mark up:** read any item inside Recall, highlight passages, add notes to them or
  to the whole item. Your notes become part of what Ask can answer from.
- **Ask, like a chat assistant, but grounded:** answers come from your library first, with
  a numbered citation on every claim; click one to land on the exact passage, highlighted.
  What your library doesn't cover is answered from the web: Recall searches, reads the top
  pages and answers only from them, citing each page and labelling the answer "from the
  web". It never answers from the model's memory, which is where made-up answers come from;
  if neither your library nor the web has it, it says so. Chats are saved and handle
  follow-ups ("tell me more", "summarize that", "explain it simply"). Choose where answers
  come from (Library, Library + Web, or Web), and type `@` to limit a question to some items
  or tags.
- **Find:** the Library's search matches each word anywhere (titles, tags, summaries, your
  notes and the full text), shows the passage where it matched, and adds documents that are
  about the same thing in other words. ⌘K jumps to any document, passage, highlight or chat.
- **Connect:** every item lists the saved items closest to it in topic, with the passage that
  links them, and the Graph page draws the whole library as a map of related items.
- **Remember:** "Quiz me" turns a document into flashcards, multiple-choice and true/false
  questions with explanations, and Review brings them back with spaced repetition, from New
  to Mastered, tracking a daily streak. Things saved a while ago and never reopened
  come back as "Worth another look".
- **Use it from your AI assistant:** Recall is an MCP server. Make a token in Settings and
  Claude, Cursor or any MCP app can search your library, ask it with citations, read items
  and save new things (see [Connect AI assistants](#connect-ai-assistants-mcp)).
- **Organise and own it:** colored tags (automatic and your own; filter by several at once,
  manage them in one place), stars, archive, rename; accounts
  keep each person's library private; export everything as Markdown and JSON at any time, or
  delete your account and all of it.

## Screenshots

| | |
| --- | --- |
| ![Library](docs/screenshots/library.jpg) | ![An item with its connections](docs/screenshots/item.jpg) |
| **Library:** search inside every document, colored tags, things worth another look | **An item:** summary, overview, key points, and what it connects to |
| ![Graph](docs/screenshots/graph.jpg) | ![Review](docs/screenshots/review.jpg) |
| **Graph:** the library as topics, with the passage linking two items | **Review:** flashcards, multiple choice and true/false, spaced out |
| ![Dark mode](docs/screenshots/dark.jpg) | ![Connect AI assistants](docs/screenshots/assistants.jpg) |
| **Dark mode,** and `@` to ask about one document | **MCP:** Claude or Cursor can search and ask your library |

## Results

Measured on 20 pinned Wikipedia articles and 46 questions, 10 of which the library can't answer.
Method, caveats and the full tables are in [`backend/eval`](backend/eval/README.md).

| Search mode | Answer passage ranked first | Answer passage in top 3 | Latency (p50) |
| --- | --- | --- | --- |
| Keyword only (Postgres full-text) | 64% | 86% | 13 ms |
| Vector only (pgvector) | 72% | 89% | 11 ms |
| **Hybrid, merged with reciprocal rank fusion** | **83%** | **92%** | 13 ms |

End to end, with Gemini answering from the top six passages:

| Measure | Result | Proposal target |
| --- | --- | --- |
| Correct source in the top 3 | 100% | 80% |
| Unanswerable questions refused | 100% (10 of 10) | |
| Answers citing the right document | 100% | |
| Answer time, p50 / p95 | 1.2 s / 1.6 s | 5 to 10 s |

What the evaluation changed: embedding each chunk with its document's title raised hybrid's
first-place rate from 72% to 83%. A cross-encoder reranker was tried as well; it got the answer into
the model's context more often (100% against 94%) but added about 0.6 s per question, so it ships
as an option (`SEARCH_MODE=rerank`) rather than the default. The "not found" threshold (0.58) was
tuned so off-topic questions never reach the LLM, while near-miss questions are left to the model,
which is told to answer `NOT_FOUND` when the passages don't hold the answer.

## How it works

- **Save:** `POST /items` stores a PDF or URL and queues a background job.
- **Process:** a worker claims jobs from Postgres (`FOR UPDATE SKIP LOCKED`), extracts text,
  chunks it, embeds each chunk locally, and asks the LLM for the summaries and tags. The LLM sees
  up to 40,000 characters, sampled from the start, middle and end of long documents, so the
  page-long summary covers the whole document. Set `SUMMARY_INPUT_CHARS` lower to send less.
- **Ask:** hybrid search (pgvector + Postgres full-text) finds the best passages; the LLM answers
  from those passages only, or says "not found in your library". In a chat, follow-ups are
  rewritten to stand alone before searching.
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

**Quickest, with Docker:** set your key and start everything (database, API with the worker
inside it, and the web app), then open http://localhost:3000 and create an account:

```bash
export GEMINI_API_KEY=your-key
docker compose up --build
```

**For development**, after the one-time setup below (steps 1 to 4), one command runs it all:

```bash
./dev.sh
```

It checks the database, applies migrations, and starts the API (with the background worker
inside it) and the web app, reloading on code changes. Ctrl+C stops everything. Steps 4 to 6
show how to run the pieces separately instead.

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
docker compose up -d db
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
| `TAVILY_API_KEY` | optional: makes web answers faster and more reliable ([free plan](https://tavily.com), 1,000 searches a month). Without it Recall uses free search engines, which rate-limit under heavy use |

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

### 8. Or try the demo library

A ready-made library of about 30 articles, papers, videos and notes, with chats, highlights
and quizzes, in its own database (yours is untouched). [`docs/demo.md`](docs/demo.md) is a
five-minute walkthrough of it.

```bash
cd backend && uv run python -m demo.seed --fresh   # builds it: about 10 minutes, needs GEMINI_API_KEY
cd .. && ./dev.sh --demo                           # log in as demo@example.com / recall-demo
```

### Troubleshooting

- **"Can't reach the Recall API"**: the API from step 4 isn't running, or it's on another port.
- **An item stays *Queued***: the worker from step 5 isn't running.
- **An item *Failed***: the message on the item says why. Scanned PDFs (images with no text)
  and pages behind a login can't be read. Fix the cause, then press *Try again*.
- **"GEMINI_API_KEY is not set"**: add the key to `backend/.env`, restart the API and the
  worker, then retry the item.
- **Gemini errors about the model**: models get retired. Set `GEMINI_MODEL` in `backend/.env`
  to a current one from [the model list](https://ai.google.dev/gemini-api/docs/models).

## Connect AI assistants (MCP)

The API serves an [MCP](https://modelcontextprotocol.io) endpoint at `/mcp` with seven tools:
`search_library`, `ask_library` (library-only, cited), `get_item`, `read_item`, `list_items`,
`list_tags` and `save_to_library`. Make a token under **Settings → Connect AI assistants**,
then, for Claude Code:

```bash
claude mcp add --transport http recall http://localhost:8000/mcp --header "Authorization: Bearer rcl_..."
```

Other apps take the same URL and header in their MCP settings. The same token also works for
the REST API (`Authorization: Bearer ...`). When deployed, set `PUBLIC_API_URL` and `WEB_URL`
so the endpoint and the links it returns use your real addresses.

## Deploy

Recall is ready to put online for free, without anything else to run: the web app on
[Vercel](https://vercel.com), the API on [Render](https://render.com) (the worker runs inside
it), and the database on [Neon](https://neon.tech).

1. **Database (Neon):** create a project and copy the connection string. Change the
   `postgresql://` prefix to `postgresql+psycopg://`, and keep `?sslmode=require`.
2. **API (Render):** New → Blueprint → this repository. It reads `render.yaml`, builds
   `backend/Dockerfile` (the embedding model is baked in) and asks for:

   | Setting | Value |
   | --- | --- |
   | `DATABASE_URL` | the Neon URL from step 1 |
   | `GEMINI_API_KEY` | your key |
   | `SIGNUP_CODE` | an invite code, so only people you give it to can sign up (leave empty for open sign-up) |
   | `FETCH_CONTACT` | your repo URL (Wikipedia requires a contact in the User-Agent) |

   `RUN_WORKER_IN_API`, `FILE_STORE=database` (uploads kept in Postgres, since free disks are
   wiped on restart) and `COOKIE_SECURE` are set by the blueprint. Migrations run on every start.
3. **Web app (Vercel):** import the repository with **Root Directory** `frontend`, and set
   `API_PROXY_TARGET` to the Render URL (like `https://recall-api.onrender.com`). The browser
   only ever talks to Vercel, which forwards `/api` to Render, so sign-in cookies are first-party.

Limits that protect the Gemini quota on a public deployment, all settings: questions per person
per minute (`ASK_PER_MINUTE`, 20) and per day (`DAILY_QUESTIONS`, 300), saved items per day
(`DAILY_ITEMS`, 200), and "quiz me" runs per day (`DAILY_QUIZZES`, 50). Free Render services
sleep when idle, so the first visit after a quiet spell takes about a minute.

## Tests

```bash
cd backend
uv run pytest                            # 98 tests, against the recall_test database
uv run ruff check . && uv run ruff format --check .
uv run python -m eval.run                # retrieval evaluation (see backend/eval)

cd ../frontend
npm run lint && npm run build
```

Tests run against a real Postgres. They use `recall_test` by default (set `DATABASE_URL` to
change it) and reset its tables, so never point them at your real library. They use a fake LLM and
a fake embedder, so they need no API key or model download.
