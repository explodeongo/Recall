# Recall

Save PDFs and web articles in one place, then ask questions in plain English and get answers built
only from your own library, with a citation to the exact passage

**[Try the live demo →](https://recall-dusky.vercel.app/demo)** No sign-up: you get your own copy of a 30-item library
(papers, articles, lectures, chats and flashcards) to save to, ask and quiz.

![CI](https://github.com/explodeongo/Recall/actions/workflows/ci.yml/badge.svg)

![Ask a question, get an answer cited from your library, open a citation: the passage, highlighted in the paper](docs/screenshots/hero.gif)

**Highlights**

- **Retrieval that's measured, not assumed.** Hybrid search (pgvector + Postgres full-text,
  merged with reciprocal rank fusion) puts the right document in the top 3 for every question in
  a 46-question evaluation that runs in CI on every push. Answers come only from retrieved
  passages: 94% of answerable questions answered, 100% of unanswerable ones refused instead of
  guessed. [Results](#results) · [engineering notes](docs/engineering-notes.md)
- **Fast:** first words on screen in 0.9 s, whole answers in 1.1 s (p50), streamed over
  Server-Sent Events; search itself takes 13 ms.
- **Every claim is checkable:** each sentence carries a numbered citation that opens the source
  with the passage highlighted, PDFs included.
- **An MCP server:** Claude, Cursor or any MCP app can search your library and get cited answers.
- **A public demo that runs on free tiers:** each visitor gets a private copy of the demo
  library in about a second (copied inside Postgres, no AI calls), deleted after a day, with a
  daily cap on AI calls so strangers can't run up the quota. [How](#deploy)
- **Built to be run, not just demoed:** a Postgres job queue (`SKIP LOCKED`, no Redis), Alembic
  migrations, ~200 tests against a real Postgres, Docker images, and CI for both apps.

## What it does

- **Save anything:** PDFs, Word, Markdown and text files, links to articles, PDFs or YouTube
  videos (read from their captions), or a note typed straight in. Paste a list of links at
  once, save the page you're on with the "Save to Recall" bookmark button, or share to Recall
  from your phone once it's installed. Each item is read in the background and gets a
  two-line summary, a page-long summary (overview, key points, section by section) and tags.
- **Read and mark up:** read any item inside Recall, with its figures where they were in the
  original, highlight passages, and add notes (with pictures: paste, drop or pick them) to
  passages or the whole item. Your notes become part of what Ask can answer from.
- **Linked ideas:** while you read, names that your other saved items are about (a method, a
  chemical, a person) are underlined; hover one to see those items and the passage in each.
  Concepts are picked out once when an item is saved; linking needs no AI call.
- **Ask, like a chat assistant, but grounded:** answers come from your library, with a
  numbered citation on every claim (numbered 1, 2, 3 in reading order); click one to land on
  the exact passage, highlighted. Each answer ends with three suggested follow-up questions.
  When your library doesn't have the answer, one click asks the web instead: Recall searches,
  reads the top pages and answers only from them, citing each page and labelling the answer
  "from the web". It never answers from the model's memory, which is where made-up answers
  come from; if nothing it found has the answer, it says so. Chats are saved, searchable, and
  handle follow-ups ("tell me more", "summarize that", "explain it simply"). Choose where
  answers come from (Library, Library + Web, or Web), and type `@` to limit a question to
  some items or tags.
- **Find:** the Library's search matches each word anywhere (titles, tags, summaries, your
  notes and the full text), shows the passage where it matched, and adds documents that are
  about the same thing in other words. ⌘K jumps to any document, passage, highlight or chat.
- **Connect:** every item lists the saved items closest to it in topic, with the passage that
  links them, and the Graph page draws the whole library as a map of related items.
- **See it:** items have covers (an article's picture, a video's thumbnail, a PDF's first
  page), the Library has a grid view, and answers show the figures beside the passages they
  cite.
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
| ![An answer with its sources and suggested follow-ups](docs/screenshots/ask.jpg) | ![Library](docs/screenshots/library.jpg) |
| **Ask:** every claim cited, figures from the sources, follow-ups to ask next | **Library:** search inside every document, colored tags, things worth another look |
| ![An item](docs/screenshots/item.jpg) | ![Graph](docs/screenshots/graph.jpg) |
| **An item:** summary, tags, notes, a quiz, and what it connects to | **Graph:** the library as topics, with the passage linking two items |
| ![Review](docs/screenshots/review.jpg) | ![Dark mode](docs/screenshots/dark.jpg) |
| **Review:** flashcards, multiple choice and true/false, spaced out, with a recap at the end | **Dark mode** |
| ![Connect AI assistants](docs/screenshots/assistants.jpg) | |
| **MCP:** Claude or Cursor can search and ask your library | |

## Results

Measured on 20 pinned Wikipedia articles and 46 questions, 10 of which the library can't answer.
Method, caveats and the full tables are in [`backend/eval`](backend/eval/README.md).

| Search mode | Right document in top 3 | Answer passage ranked first | Answer passage in top 3 | Latency (p50) |
| --- | --- | --- | --- | --- |
| Keyword only (Postgres full-text) | 97% | 61% | 89% | 12 ms |
| Vector only (pgvector) | 100% | 67% | 92% | 11 ms |
| **Hybrid, merged with reciprocal rank fusion** | **100%** | **81%** | **92%** | 13 ms |

End to end, with Gemini answering from the top six passages:

| Measure | Result | Proposal target |
| --- | --- | --- |
| Correct source in the top 3 | 100% | 80% |
| Answerable questions answered | 94% | |
| Unanswerable questions refused | 100% (10 of 10) | |
| Answers citing the right document | 100% | |
| Answer time, p50 / p95 | 1.1 s / 1.5 s | 5 to 10 s |
| First words on screen, p50 | 0.9 s | |

What the evaluation changed:

- Embedding each chunk with its document's title raised hybrid's first-place rate from 72% to 83%.
- A cross-encoder reranker got the answer into the model's context more often (100% against 94%)
  but added about 0.6 s per question, so it ships as an option (`SEARCH_MODE=rerank`), not the
  default.
- Dropping reference lists and navigation lines from extracted text cut the index by a third
  (390 to 265 chunks) with end-to-end answers unchanged; a question-by-question comparison showed
  the one first-place swap was chunk boundaries moving, not lost text. The story is in the
  [engineering notes](docs/engineering-notes.md).
- The "not found" threshold (0.58) was tuned so off-topic questions never reach the LLM, while
  near-miss questions are left to the model, which is told to answer `NOT_FOUND` when the
  passages don't hold the answer.

## How it works

```mermaid
flowchart TB
    subgraph Save["Save (background job)"]
        direction TB
        S1["PDF · link · video · note"] --> S2["Extract text<br/>and figures"]
        S2 --> S3["Clean: headers, page numbers,<br/>navigation, reference lists"]
        S3 --> S4["Chunk ~400 tokens<br/>with overlap"]
        S4 --> S5["Embed locally<br/>bge-small (ONNX)"]
        S3 --> S6["Gemini: summaries,<br/>tags, key concepts"]
    end

    subgraph Ask["Ask (streamed)"]
        direction TB
        A1["Question"] --> A2["Rewrite follow-ups<br/>to stand alone"]
        A2 --> A3["Hybrid search:<br/>pgvector HNSW + full-text,<br/>reciprocal rank fusion"]
        A3 --> A4{"Closest passage<br/>similar enough?"}
        A4 -- no --> A5["Not in your library<br/>(no LLM call)"]
        A4 -- yes --> A6["Gemini answers from<br/>the top 6 passages only"]
        A6 --> A7["Cited answer over SSE,<br/>suggested follow-ups"]
        A5 -. one click .-> W["Web search: read the top<br/>pages, answer from them"]
    end

    DB[("Postgres<br/>items · chunks · vectors<br/>jobs queue")]
    S5 --> DB
    S6 --> DB
    DB --> A3
    MCP["Claude · Cursor<br/>(MCP server)"] --> A1
```

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

It's online at [recall-dusky.vercel.app/demo](https://recall-dusky.vercel.app/demo), no sign-up needed. To run it locally: a ready-made library of about 30 articles, papers, videos and notes, with chats, highlights
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

Recall runs online for free: the web app on [Vercel](https://vercel.com), the API on
[Render](https://render.com) (the worker runs inside it), and the database on
[Neon](https://neon.tech). With the demo on, anyone can open `/demo` and get a private copy of
the demo library for a day, without signing up.

1. **Database (Neon):** create a project (Postgres 17) and copy its connection string.
2. **Demo library:** build it locally once (`uv run python -m demo.seed`), then copy it into
   Neon. This creates the tables, copies the library and moves its pictures and PDFs into the
   database:

   ```bash
   cd backend
   uv run python -m demo.publish "postgresql://...neon.tech/neondb?sslmode=require"
   ```

3. **API (Render):** New → Blueprint → this repository. It reads `render.yaml`, builds
   `backend/Dockerfile` (the embedding model is baked in) and asks for:

   | Setting | Value |
   | --- | --- |
   | `DATABASE_URL` | the Neon URL, starting `postgresql+psycopg://` instead of `postgresql://` |
   | `GEMINI_API_KEY` | a key made for the deployment, separate from your local one |
   | `SIGNUP_CODE` | an invite code, so only people you give it to can make accounts |
   | `FETCH_CONTACT` | your repo URL (Wikipedia requires a contact in the User-Agent) |

   The blueprint also sets `RUN_WORKER_IN_API`, `FILE_STORE=database` (free disks are wiped on
   restart), `COOKIE_SECURE`, the demo (`GUEST_TEMPLATE_EMAIL`) and `DAILY_LLM_CALLS=400`, a
   cap on Gemini calls a day across everyone. Migrations run on every start.
4. **Web app (Vercel):** import the repository with **Root Directory** `frontend`, and set
   `API_PROXY_TARGET` to the Render URL (like `https://recall-api.onrender.com`). The browser
   only talks to Vercel, which forwards `/api` to Render, so sign-in cookies are first-party.
5. **Keep it awake:** in the GitHub repository, add the Actions variable `RECALL_API_URL` (the
   Render URL). [`keep-awake.yml`](.github/workflows/keep-awake.yml) pings it every 10 minutes,
   so visitors don't wait a minute for a sleeping server.

**How the demo stays safe and free** ([`services/guest.py`](backend/app/services/guest.py)):
each visitor gets their own copy of the library, made inside the database in about 0.3 s with
no LLM calls, so nobody sees anyone else's questions. Copies share the template's files and are
deleted after 24 hours (or sooner when more than 40 are open), checked whenever a new visitor
arrives, so no scheduled job is needed. Guests get smaller daily limits (30 questions, 5 saves,
3 quizzes, 5 MB uploads), can't make API tokens, and the template account can't be logged into.
When the day's Gemini calls run out, answers say so and come back tomorrow; search, reading, the
graph and review need no LLM and keep working.

Limits for everyone else, all settings: questions per person per minute (`ASK_PER_MINUTE`, 20)
and per day (`DAILY_QUESTIONS`, 300), saved items per day (`DAILY_ITEMS`, 200), and "quiz me"
runs per day (`DAILY_QUIZZES`, 50).

## Tests

```bash
cd backend
uv run pytest                            # 206 tests, against the recall_test database
uv run ruff check . && uv run ruff format --check .
uv run python -m eval.run                # retrieval evaluation (see backend/eval)

cd ../frontend
npm run lint && npm run build
```

Tests run against a real Postgres. They use `recall_test` by default (set `DATABASE_URL` to
change it) and reset its tables, so never point them at your real library. They use a fake LLM and
a fake embedder, so they need no API key or model download.
