# Recall evaluation results

Generated 2026-10-27 at commit `74532f5+uncommitted changes` by `python -m eval.run --llm`. 20 documents (265 chunks), 36 answerable and 10 unanswerable questions. Embeddings: BAAI/bge-small-en-v1.5; chunks of about 400 tokens; top 6 passages sent to the model.

## Retrieval: hybrid vs vector-only vs keyword-only, with and without reranking

**Source recall@3**: the expected document is among the top 3 documents retrieved (the proposal's measure). **Passage@k**: the passage that actually contains the answer is ranked in the top k; this is the stricter test, since the model leans on the top passages. *In context*: the answer is anywhere in the 6 passages sent to the model.

| Mode | Source recall@3 | Source MRR | Passage@1 | Passage@3 | In context | p50 / p95 latency |
| --- | --- | --- | --- | --- | --- | --- |
| hybrid | **100%** | 0.97 | 81% | **92%** | 94% | 13 / 18 ms |
| vector | **100%** | 0.94 | 67% | **92%** | 97% | 11 / 13 ms |
| keyword | **97%** | 0.96 | 61% | **89%** | 92% | 12 / 16 ms |
| rerank | **100%** | 1.00 | 83% | **92%** | 97% | 668 / 895 ms |

Passage@3 by question style: *paraphrase* questions avoid the document's own words, *keyword* questions use its names and jargon.

| Mode | Paraphrase | Keyword |
| --- | --- | --- |
| hybrid | 88% (n=17) | 95% (n=19) |
| vector | 82% (n=17) | 100% (n=19) |
| keyword | 82% (n=17) | 95% (n=19) |
| rerank | 88% (n=17) | 95% (n=19) |

## Saying "not found"

Before calling the LLM, Recall refuses when the closest passage's cosine similarity is below a threshold. The threshold was swept over this question set:

- Highest threshold that blocks no answerable question: **0.60**. It refuses 50% of unanswerable questions without an LLM call.
- At the configured threshold (0.58): refuses 50% and lets through 100%.
- Closest-passage similarity: answerable questions 0.60 to 0.89, unanswerable 0.44 to 0.69.

The threshold is tuned on the same questions it is scored on, so these numbers are optimistic. Questions the gate lets through can still be refused by the model, which is told to reply NOT_FOUND when the passages don't hold the answer (see below).

## End-to-end answers (gemini-3.5-flash-lite, hybrid search)

| Measure | Result | Proposal target |
| --- | --- | --- |
| Answerable questions answered | 94% | |
| Unanswerable questions refused | 100% | |
| Answers citing the expected document | 100% | |
| Answer time, p50 / p95 | 1.1 s / 1.5 s | 5 to 10 s |
| First words on screen, p50 | 0.9 s | |

Faithfulness (target: at least 90% of sampled answers supported by the cited passage) is checked by hand in `eval/review/faithfulness.csv`; summary and tag quality (target: 4 out of 5) in `eval/review/summaries.csv`.
