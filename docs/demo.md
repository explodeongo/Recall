# Recall demo: a five-minute walkthrough

A script for showing Recall live, on the demo library. Times are a guide; the bold lines are
what to say, the rest is what to click. Practise it twice with a timer.

## Before you start (10 minutes earlier)

1. **Build the demo library** if you haven't, or rebuild it fresh (5 to 10 minutes; needs the
   internet and `GEMINI_API_KEY` in `backend/.env`):

   ```bash
   cd backend && uv run python -m demo.seed --fresh
   ```

2. **Start Recall on it:** stop your usual `./dev.sh` if it's running (same ports), run
   `./dev.sh --demo`, then open http://localhost:3000 and log in as
   `demo@example.com`, password `recall-demo`. Your own library isn't touched.
3. Light theme, browser zoom 110% so the back row can read it, other tabs closed.
4. Warm it up: open Ask once and ask anything, so the first real question isn't the slow one.
5. Have one link ready to paste: `https://en.wikipedia.org/wiki/Reciprocal_rank_fusion`.
6. No internet? Use your phone's hotspot. Answers need Gemini; nothing else does.

## The walkthrough

### 0:00 The problem (20 s)

> **"I save articles, papers and videos all the time, and a month later I can't find them or
> remember what they said. Recall is a personal library that reads everything I save, and
> lets me ask it questions with answers that point to the exact passage."**

Show the Library: thirty-odd things saved over six weeks, each with a short summary and
colored tags. Point at **Worth another look**: things saved a while ago and never reopened.

### 0:20 Save something (40 s)

Click **Add item**, paste the Reciprocal rank fusion link, save.

> **"It fetches the page, writes a summary and a page-long overview, tags it, and splits it
> into passages it can search. No setup, no folders."**

While it reads (about 15 seconds), go on; come back to it at the end of the next step.

### 1:00 Find things (40 s)

Type `forgetting` in the search box.

> **"Search matches words anywhere, inside the full text too, and shows the passage where it
> matched. Things about the same subject in other words come after, marked Related."**

Click two tags (say `#information retrieval` and `#search engines`) and flip **All / Any**.

> **"Tags come from the AI, but they're mine to change: colors, renames, merges. Filtering
> never calls the AI."** Open the item just saved: its summary is there.

### 1:40 Ask (80 s)

Open **Ask** and ask: *How does BM25 decide which documents rank highest?*

> **"Every claim has a numbered source."** Hover a number to preview the passage, click it:
> the item opens with that exact passage highlighted.

Follow up: *How is that different from how a vector database finds matches?*

> **"It understands follow-ups like a chat assistant, but it only answers from what I saved."**

Now ask: *When is keyword search better than semantic search?*

> **"Nothing I saved compares them head on, so it says so and answers from the web instead,
> labelled, with the pages cited. It never answers from the model's own memory."**

Type `@Attention`, pick the paper, ask: *What problem does self-attention solve?*

> **"The @ limits an answer to one document, or to everything with a tag."**

### 3:00 Connections (40 s)

Open **Attention Is All You Need** and scroll to **Connected in your library**.

> **"Recall links what I save. This paper connects to the transformer video and the
> embeddings article, and it shows me the passage that links them."**

Click **See the graph**.

> **"Here's the whole library: items gather into topics, named after the tags they share.
> Hollow dots are things that don't connect to anything yet."** Click a dot to show its panel.

### 3:40 Remember it (40 s)

Open **Review**, answer one multiple-choice question wrong on purpose, then one right.

> **"Quiz me turns any item into questions: flashcards, multiple choice, true or false, each
> with an explanation. Spaced repetition brings each one back just before I'd forget it."**

### 4:20 Use it anywhere (25 s)

Open **Settings → Connect AI assistants**.

> **"Recall is also an MCP server: with one command, Claude or Cursor can search my library
> and get the same cited answers inside the tools I already use."**

### 4:45 Close (15 s)

> **"On our evaluation set, the right document is in the top three results every time,
> the passage with the answer is in the top three 92% of the time, it refused every
> question the library couldn't answer, and answers start in about a second."**

## Likely questions

- **How do you stop it making things up?** The model only sees passages retrieved from your
  library (or web pages it just read) and is told to answer only from them; a similarity
  gate refuses before calling the model when nothing relevant is found. On the evaluation
  set it refused 100% of unanswerable questions, and answers cited the expected document
  100% of the time.
- **How does search work?** Hybrid: Postgres full-text search and vector similarity
  (pgvector, bge-small embeddings computed locally), merged with reciprocal rank fusion.
  Hybrid beat either alone on passage ranking (Passage@1 81% vs 67% and 61%).
- **What does it cost to run?** Nothing. Embeddings run locally; summaries and answers use
  Gemini's free tier. It runs on a laptop with Postgres, and online on free tiers (Vercel,
  Render, Neon) at recall-dusky.vercel.app/demo, where every visitor gets a private copy of
  the demo library and a daily cap keeps AI calls inside the free quota.
- **Is my data private?** Each account sees only its own library; you can export everything
  as Markdown and JSON, or delete your account and all of it.
- **What would you do next?** A browser extension for one-click saving, key moments for
  videos, and saving answers as notes.

## If something goes wrong

- **A save fails** (some sites block readers): say so, it's shown on the item with a
  "Read again" button, and move on with the demo library.
- **Gemini is slow or rate-limited:** answers fall back to a second model; if both are busy,
  show a chat already in the history (the left column of Ask has four).
- **Total failure:** open the live demo, recall-dusky.vercel.app/demo, from any laptop; failing
  that, the README's GIF and screenshots show every screen.
