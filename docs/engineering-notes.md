# Engineering notes

Decisions that shaped Recall, each with the evidence behind it. The numbers come from the
evaluation in [`backend/eval`](../backend/eval/README.md): 20 pinned Wikipedia articles and
46 questions, 10 of which the library can't answer, run in CI on every push.

## 1. A metric got worse, and the change shipped anyway

**The change.** Text extracted from web pages carried a lot that isn't the article: "Part of a
series on…" navigation, "This article is about…" notes, and long reference lists. These were
being chunked and embedded like everything else, so a question could retrieve a bibliography
entry instead of the paragraph that answers it. I added cleaning that drops navigation lines,
and, once a document's references begin in its later part, drops the reference entries.

**The first result looked bad.** Hybrid search ranked the answer passage first 81% of the
time instead of 83%, vector-only went from 72% to 67%, and keyword-only from 64% to 61%. The
project's rule is that search changes ship only if the numbers hold up, so this needed
explaining, not ignoring.

**What the breakdown showed.** The evaluation only reported totals, so I made it record each
question's passage rank and ran it twice, with the old cleaning and the new:

- No answer text had been removed from any document. I checked every eval answer against the
  cleaned text of its document.
- In hybrid search, one question moved, from rank 1 to rank 2. With 18% fewer chunks, chunk
  boundaries had shifted; that is noise at this sample size, not lost information.
- One question, about HTTP/2, now ranked a *citation* above its answer. That exposed the real
  bug: Wikipedia footnotes start with "↑" or back-link numbers ("1 2 Cormen…"), and dates are
  written "Retrieved September 20, 2014", so most footnotes slipped past the reference check.
  In the HTTP/2 page, about 10k of its 12k characters of references survived.

**The fix and the outcome.** Footnote back-links now count as a reference marker on their own.
The index shrank from 390 chunks to 265 (32% smaller). End-to-end answers were unchanged (94%
answered, 100% refused, 100% citing the right document), and first words arrived no later
(0.9 s p50, against 1.2 s before). Rerank's rank for the HTTP/2 question
improved from 4 to 2. The one keyword-only miss that appeared had been a "hit" on a
bibliography title, so it wasn't a real loss.

**What I took from it.** An aggregate dip on a 36-question set can be one question. Per-question
diffs are cheap to keep, and they turned an ambiguous number into a specific bug.

## 2. Refuse before calling the model

Answers must come only from retrieved passages, so the riskiest moment is when nothing relevant
was retrieved and the model is tempted to answer from memory. Two guards handle it:

- **A similarity gate.** If the closest passage's cosine similarity is below 0.58, Recall says
  "not in your library" without calling the LLM. Answerable questions' best passages scored
  0.60 to 0.89 and unanswerable ones 0.44 to 0.69, so the gate is set where it never blocks a
  real question, and it refuses half of the unanswerable ones for free.
- **A sentinel.** For near misses the gate lets through, the model is told to reply
  `NOT_FOUND` when the passages don't hold the answer. Together they refuse 10 of 10
  unanswerable questions.

The threshold is tuned on the questions it is scored on, which the results say plainly.

## 3. Small retrieval changes, measured

- **Title in every chunk's embedding.** A passage deep inside a document often doesn't name its
  subject. Embedding each chunk with its document's title in front raised hybrid search's
  first-place rate from 72% to 83% at the time (81% today, after the cleaning above).
- **Hybrid over either alone.** Keyword search is precise on names and jargon, vectors on
  paraphrase. Merging them with reciprocal rank fusion puts the answer passage in the top 3 for
  92% of questions and the right document in the top 3 for all of them, in 13 ms.
- **A reranker, kept optional.** A cross-encoder got the answer into the model's context more
  often (97% against 94% now) but added about 0.6 s per question. It ships as
  `SEARCH_MODE=rerank`, not the default.

## 4. The web is one click away, not the default

Recall can answer from the web: it searches, reads the top pages and answers only from them,
citing each page. It used to do this automatically when the library fell short. That blurred
the product's promise ("answers from what *you* saved"), so the default is now the library
alone, and a "not found" answer offers "Search the web instead". The web answer is labelled as
such and still never comes from the model's memory.

## 5. Citations people can follow

The model cites passages by search rank, so an answer could read "[2][3]" with no [1], and a
reader would go looking for the missing source. Citations are renumbered 1, 2, 3 in the order
the answer first uses them, everywhere: in the chat, copied text, and answers saved as notes.
The renumbering is done on the client while the answer streams. That is safe because the order
of first appearance never changes as text is added, so a chip's number never flips mid-answer.
Clicking one opens the source with the passage highlighted, and figures above it reserve their
space so the highlight doesn't slide away when they load.

## 6. Boring infrastructure on purpose

- **Jobs in Postgres.** Saving queues a job in a `jobs` table; the worker claims work with
  `FOR UPDATE SKIP LOCKED` and retries with backoff. That's one database to run instead of a
  database and Redis, and a job is never lost between them.
- **One LLM interface.** Everything calls `LLMClient`; the Gemini client behind it tries a
  fallback model when one is overloaded, waits briefly and tries again when all are, and tells
  the user plainly that "Gemini is busy" instead of showing a provider error.
- **Tests against real Postgres.** About 200 tests run against a throwaway Postgres with
  pgvector, not mocks, so SQL, vector search and migrations are what's tested.

## 7. A public demo nobody can break or run up

The live demo ([recall-dusky.vercel.app/demo](https://recall-dusky.vercel.app/demo)) had to work for a stranger in one
click, on free hosting, without letting visitors see each other's questions or exhaust the
Gemini quota.

- **A private copy per visitor.** "Try the demo" copies the demo account's library into a new
  guest account: items, passages with their vectors, tags, notes, highlights, pictures, chats
  and flashcards. The passages are copied with `INSERT … SELECT` inside Postgres, ids are
  remapped (chat citations point at the copy's passages and pictures), and dates shift so the
  library always looks a few weeks old. It takes about a second and makes no AI calls.
- **Shared files, never deleted.** Copies point at the template's PDFs and pictures instead of
  duplicating them; deleting a file checks the template still doesn't use it.
- **Clean-up without a scheduler.** Guests older than a day, or beyond the 40 newest, are
  deleted whenever a new one arrives, which bounds the database (about 5 MB a guest) without a
  paid cron job.
- **A quota that can't be drained.** A daily cap on AI calls across everyone is counted in
  Postgres. Past it, answers say they're back tomorrow, while search, reading, the graph and
  review, which need no AI, keep working. Guests also get smaller per-day limits.
- **Free tiers, used carefully.** The API sits in the same region as the database, since a
  guest's copy is many small queries. Health checks and the keep-awake ping use a route that
  doesn't touch the database, so the free database can still sleep when nobody's there.
