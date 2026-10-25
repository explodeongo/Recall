# Evaluation

How well does Recall find the right passage, refuse what it doesn't know, and answer quickly?
This folder measures it, following section 7 of the proposal. The latest numbers are in
[`results.md`](results.md).

## What's here

| File | What it is |
| --- | --- |
| `corpus/` and `corpus.json` | 20 Wikipedia articles pinned to exact revisions (CC BY-SA 4.0) |
| `questions.jsonl` | 36 answerable questions with the expected article and an answer phrase, plus 10 the library can't answer |
| `run.py` | The evaluation: loads the corpus into its own database and scores every search mode |
| `fetch_corpus.py` | Re-snapshots the corpus (only needed to change it) |
| `results.md`, `results.json` | The latest full run, committed |
| `review/` | Sheets for the manual checks: answer faithfulness and summary/tag quality |
| `usability-test.md` | Script, task card and questionnaire for the classmate usability test |

## Run it

```bash
cd backend
uv run python -m eval.run          # retrieval only: no API key, about 30 s
uv run python -m eval.run --llm    # also answers every question with Gemini: about 5 min
```

It loads the corpus into `EVAL_DATABASE_URL` (default: a local `recall_eval` database, created if
missing) and refuses any database whose name doesn't end in `_eval` or `_test`, so it can't
touch your library. CI runs the retrieval part on every push and fails if hybrid recall@3 falls
below the proposal's 80% target.

## How the questions were built

- **Answerable (36):** each names its expected article and a short answer phrase.
  `tests/test_eval_data.py` checks in CI that every phrase really is in that article.
- **Two styles:** *paraphrase* questions avoid the article's own wording ("automatic reclamation
  of unused memory" for garbage collection), *keyword* questions use its names and jargon
  ("TCP CUBIC"). Vector search should win the first kind and keyword search the second.
- **Unanswerable (10):** five off-topic ("the capital of Australia") and five near misses that
  sound like they belong in this library but aren't covered (Kubernetes scheduling, quicksort,
  the Rust borrow checker, ResNet's learning rate, GraphQL). Each was checked against the corpus.

## Metrics

- **Source recall@3, MRR:** is the expected article among the top three articles retrieved?
  This is the proposal's retrieval measure.
- **Passage@1, passage@3:** is the passage that *contains the answer phrase* ranked first, or in
  the top three? Stricter, and closer to what the model relies on.
- **In context:** is the answer anywhere in the passages sent to the model?
- **Not-found gate:** for a sweep of similarity thresholds, the share of unanswerable questions
  refused and of answerable questions let through.
- **End to end (`--llm`):** answered rate, refusal rate, whether answers cite the expected
  article, and answer latency (p50 and p95, plus time to the first words).

## Caveats

- 36 questions is a small set: one question is about 3 points. Treat differences of a few points
  as noise.
- The similarity threshold is tuned on the same questions it's scored on, so the gate numbers
  are optimistic. A held-out set would fix this.
- The questions were written by the person who built the system, after reading the articles.
- Faithfulness and summary quality are judged by hand (`review/`), as the proposal specifies.
