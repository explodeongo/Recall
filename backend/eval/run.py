"""Recall's evaluation (proposal section 7): python -m eval.run [--llm] [--min-recall 0.8]

Loads the pinned corpus into a separate database, then measures, for each search mode
(hybrid, vector-only, keyword-only):

- retrieval: hit@1, recall@3 and MRR at the document level, and whether the answer text is in
  the passages that would be sent to the LLM
- "not found": how well the similarity gate separates answerable from unanswerable questions,
  across a sweep of thresholds
- retrieval latency at p50 and p95

Retrieval needs no API key (embeddings are local), so CI runs this part on every push.
With --llm it also answers every question through Gemini, times the answers, and writes review
sheets for the manual faithfulness and summary checks.

The corpus is loaded into EVAL_DATABASE_URL (default: a local recall_eval database), never
into your library; the script refuses to touch a database whose name doesn't end in _eval or
_test.
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

HERE = Path(__file__).parent
DEFAULT_DB = "postgresql+psycopg://recall:recall@localhost:5432/recall_eval"

# The app reads DATABASE_URL when it's first imported, so point it at the eval database first.
os.environ["DATABASE_URL"] = os.environ.get("EVAL_DATABASE_URL", DEFAULT_DB)

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.config import get_settings  # noqa: E402

THRESHOLDS = [round(0.40 + 0.01 * i, 2) for i in range(41)]  # 0.40 to 0.80


# --- data ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    doc: str | None  # None: the library can't answer it
    answer: str | None
    style: str


def load_questions() -> list[Question]:
    rows = [json.loads(line) for line in (HERE / "questions.jsonl").read_text().splitlines()]
    return [Question(r["id"], r["question"], r["doc"], r.get("answer"), r["style"]) for r in rows]


class SnapshotSource:
    """Feeds a committed corpus snapshot to the pipeline instead of fetching it."""

    def __init__(self, doc_id: str, title: str):
        self.doc_id, self.title = doc_id, title

    def extract(self, item):
        from app.sources import ExtractedDoc, PageText

        body = (HERE / "corpus" / f"{self.doc_id}.txt").read_text()
        return ExtractedDoc(title=self.title, pages=[PageText(page=None, text=body)])


# --- database ------------------------------------------------------------------------------


def prepare_database() -> None:
    url = make_url(os.environ["DATABASE_URL"])
    if not url.database or not url.database.endswith(("_eval", "_test")):
        sys.exit(f"Refusing to load the eval corpus into '{url.database}': use a *_eval database")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()

    from alembic.config import Config

    from alembic import command

    cfg = Config(str(HERE.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(HERE.parent / "alembic"))
    command.upgrade(cfg, "head")

    from app.db import engine

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE items, tags, jobs RESTART IDENTITY CASCADE"))


def ingest(session, embedder, llm) -> tuple[dict[int, str], dict]:
    from app.models import Item, ItemStatus, SourceType
    from app.pipeline import process_item

    manifest = json.loads((HERE / "corpus.json").read_text())
    item_doc: dict[int, str] = {}
    started = time.perf_counter()
    for doc in manifest:
        item = Item(title=doc["title"], source_type=SourceType.url, source=doc["url"])
        session.add(item)
        session.flush()
        source = SnapshotSource(doc["id"], doc["title"])
        process_item(session, item, embedder=embedder, llm=llm, source=source)
        item.status = ItemStatus.ready
        session.commit()
        item_doc[item.id] = doc["id"]
        if llm is not None:
            time.sleep(PACE_S)
    seconds = time.perf_counter() - started
    chunks = session.scalar(text("SELECT count(*) FROM chunks"))
    return item_doc, {"documents": len(manifest), "chunks": chunks, "ingest_s": seconds}


# --- retrieval -----------------------------------------------------------------------------


@dataclass
class ModeResult:
    mode: str
    ranks: dict[str, int | None] = field(default_factory=dict)  # question id -> doc rank
    # question id -> rank of the first passage that contains the answer text
    passage_ranks: dict[str, int | None] = field(default_factory=dict)
    latencies_ms: list[float] = field(default_factory=list)


def evaluate_retrieval(session, embedder, questions, item_doc, mode) -> ModeResult:
    from app.services.rerank import get_reranker
    from app.services.search import SearchMode, search

    settings = get_settings()
    reranker = get_reranker() if mode == SearchMode.rerank else None
    if reranker is not None:
        reranker.score("warm up", ["warm up"])  # keep model start-up out of the latency numbers
    result = ModeResult(mode)
    for q in questions:
        if q.doc is None:
            continue
        started = time.perf_counter()
        found = search(
            session,
            embedder,
            q.question,
            mode=mode,
            k=settings.answer_k,
            candidate_k=settings.candidate_k,
            reranker=reranker,
            rerank_pool=settings.rerank_pool,
        )
        result.latencies_ms.append((time.perf_counter() - started) * 1000)
        docs = list(dict.fromkeys(item_doc[p.item_id] for p in found.passages))
        result.ranks[q.id] = docs.index(q.doc) + 1 if q.doc in docs else None
        hits = [i for i, p in enumerate(found.passages, 1) if q.answer.lower() in p.text.lower()]
        result.passage_ranks[q.id] = hits[0] if hits else None
    return result


def retrieval_metrics(result: ModeResult, questions: list[Question], style: str | None = None):
    ids = [q.id for q in questions if q.doc is not None and (style is None or q.style == style)]
    ranks = [result.ranks[i] for i in ids]
    passages = [result.passage_ranks[i] for i in ids]
    return {
        "n": len(ids),
        "hit@1": mean(r == 1 for r in ranks),
        "recall@3": mean(r is not None and r <= 3 for r in ranks),
        "mrr": mean(1 / r if r else 0.0 for r in ranks),
        "passage@1": mean(r == 1 for r in passages),
        "passage@3": mean(r is not None and r <= 3 for r in passages),
        "passage_mrr": mean(1 / r if r else 0.0 for r in passages),
        "answer_in_context": mean(r is not None for r in passages),
    }


def best_similarities(session, embedder, questions) -> dict[str, float]:
    from app.services.search import search

    sims = {}
    for q in questions:
        found = search(session, embedder, q.question, k=1)
        sims[q.id] = found.best_similarity or 0.0
    return sims


def gate_sweep(sims: dict[str, float], questions: list[Question]) -> list[dict]:
    """For each threshold: share of unanswerable questions refused, and of answerable ones
    let through. Balanced accuracy is their mean."""
    answerable = [sims[q.id] for q in questions if q.doc is not None]
    unanswerable = [sims[q.id] for q in questions if q.doc is None]
    rows = []
    for t in THRESHOLDS:
        refused = mean(s < t for s in unanswerable)
        answered = mean(s >= t for s in answerable)
        rows.append(
            {
                "threshold": t,
                "refusal_recall": refused,
                "answer_rate": answered,
                "balanced": (refused + answered) / 2,
            }
        )
    return rows


def pick_threshold(rows: list[dict]) -> dict:
    """The highest threshold that still lets every answerable question through: the gate's job
    is to skip the LLM for clearly off-topic questions, never to block a real one. Questions
    that are close in topic but unanswered are left to the model's NOT_FOUND reply."""
    safe = [r for r in rows if r["answer_rate"] == 1.0]
    return max(safe, key=lambda r: r["threshold"]) if safe else rows[0]


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    k = max(0, min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1))))
    return ordered[k]


# --- answers (needs GEMINI_API_KEY) --------------------------------------------------------

PACE_S = 4.0  # seconds between LLM calls, to stay inside the free tier's per-minute limit


def call_with_retry(fn, attempts: int = 5):
    from app.services.llm import LLMError

    for attempt in range(attempts):
        try:
            return fn()
        except LLMError as exc:
            if not exc.retryable or attempt == attempts - 1:
                raise
            wait = 10 * 2**attempt
            print(f"  rate limited or busy, retrying in {wait}s: {str(exc)[:80]}", flush=True)
            time.sleep(wait)
    raise AssertionError("unreachable")


def evaluate_answers(session, embedder, llm, questions, item_doc) -> list[dict]:
    from app.services.answer import answer_question

    rows = []
    for i, q in enumerate(questions, 1):
        result = call_with_retry(lambda q=q: answer_question(session, embedder, llm, q.question))
        t = result.timings
        cited = [result.sources[n - 1] for n in result.cited]
        rows.append(
            {
                "id": q.id,
                "question": q.question,
                "expected_doc": q.doc or "",
                "not_found": result.not_found,
                "answer": result.text,
                "cited_docs": sorted({item_doc[s.item_id] for s in cited}),
                "cited_passages": [s.text for s in cited],
                "total_ms": t.retrieval_ms + t.llm_ms,
                "first_token_ms": t.first_token_ms,
                "llm_called": t.llm_ms > 0,
            }
        )
        print(f"  [{i}/{len(questions)}] {q.id} {'not found' if result.not_found else 'answered'}")
        if t.llm_ms > 0:
            time.sleep(PACE_S)
    return rows


def answer_metrics(rows: list[dict]) -> dict:
    answerable = [r for r in rows if r["expected_doc"]]
    unanswerable = [r for r in rows if not r["expected_doc"]]
    answered = [r for r in answerable if not r["not_found"]]
    timed = [r["total_ms"] for r in rows if r["llm_called"]]
    first = [r["first_token_ms"] for r in rows if r["first_token_ms"] is not None]
    return {
        "answered_rate": mean(not r["not_found"] for r in answerable),
        "refusal_recall": mean(r["not_found"] for r in unanswerable),
        "cites_expected_doc": (
            mean(r["expected_doc"] in r["cited_docs"] for r in answered) if answered else 0.0
        ),
        "answer_p50_ms": percentile(timed, 50),
        "answer_p95_ms": percentile(timed, 95),
        "first_token_p50_ms": percentile(first, 50),
    }


def write_review_sheets(rows: list[dict], session) -> None:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models import Item

    out = HERE / "review"
    out.mkdir(exist_ok=True)
    with (out / "faithfulness.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "question", "answer", "cited passages", "supported (y/n)", "notes"])
        for r in rows:
            if not r["not_found"]:
                passages = "\n---\n".join(r["cited_passages"])
                w.writerow([r["id"], r["question"], r["answer"], passages, "", ""])
    items = session.scalars(select(Item).options(selectinload(Item.tags)).order_by(Item.id))
    with (out / "summaries.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["title", "summary", "tags", "summary score (1-5)", "tags score (1-5)"])
        for item in items:
            w.writerow([item.title, item.summary, ", ".join(t.name for t in item.tags), "", ""])


# --- report --------------------------------------------------------------------------------


def pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def git_commit() -> str:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "."], capture_output=True, text=True, check=True
        ).stdout.strip()
        return f"{head}+uncommitted changes" if dirty else head
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def render(report: dict) -> str:
    s = report["setup"]
    lines = [
        "# Recall evaluation results",
        "",
        f"Generated {s['generated']} at commit `{s['commit']}` by `python -m eval.run"
        f"{' --llm' if report.get('answers') else ''}`. "
        f"{s['documents']} documents ({s['chunks']} chunks), "
        f"{s['answerable']} answerable and {s['unanswerable']} unanswerable questions. "
        f"Embeddings: {s['embedding_model']}; chunks of about {s['chunk_tokens']} tokens; "
        f"top {s['answer_k']} passages sent to the model.",
        "",
        "## Retrieval: hybrid vs vector-only vs keyword-only, with and without reranking",
        "",
        "**Source recall@3**: the expected document is among the top 3 documents retrieved "
        "(the proposal's measure). **Passage@k**: the passage that actually contains the answer "
        "is ranked in the top k; this is the stricter test, since the model leans on the top "
        f"passages. *In context*: the answer is anywhere in the {report['setup']['answer_k']} "
        "passages sent to the model.",
        "",
        "| Mode | Source recall@3 | Source MRR | Passage@1 | Passage@3 | In context "
        "| p50 / p95 latency |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for mode, m in report["retrieval"].items():
        a = m["all"]
        lines.append(
            f"| {mode} | **{pct(a['recall@3'])}** | {a['mrr']:.2f} | {pct(a['passage@1'])} | "
            f"**{pct(a['passage@3'])}** | {pct(a['answer_in_context'])} | "
            f"{m['p50_ms']:.0f} / {m['p95_ms']:.0f} ms |"
        )
    lines += [
        "",
        "Passage@3 by question style: *paraphrase* questions avoid the document's own words, "
        "*keyword* questions use its names and jargon.",
        "",
        "| Mode | Paraphrase | Keyword |",
        "| --- | --- | --- |",
    ]
    for mode, m in report["retrieval"].items():
        lines.append(
            f"| {mode} | {pct(m['paraphrase']['passage@3'])} (n={m['paraphrase']['n']}) | "
            f"{pct(m['keyword']['passage@3'])} (n={m['keyword']['n']}) |"
        )
    g = report["gate"]
    lines += [
        "",
        '## Saying "not found"',
        "",
        "Before calling the LLM, Recall refuses when the closest passage's cosine similarity is "
        "below a threshold. The threshold was swept over this question set:",
        "",
        f"- Highest threshold that blocks no answerable question: **{g['best']['threshold']:.2f}**."
        f" It refuses {pct(g['best']['refusal_recall'])} of unanswerable questions without an "
        "LLM call.",
        f"- At the configured threshold ({g['configured']['threshold']:.2f}): refuses "
        f"{pct(g['configured']['refusal_recall'])} and lets through "
        f"{pct(g['configured']['answer_rate'])}.",
        f"- Closest-passage similarity: answerable questions "
        f"{g['answerable_min']:.2f} to {g['answerable_max']:.2f}, unanswerable "
        f"{g['unanswerable_min']:.2f} to {g['unanswerable_max']:.2f}.",
        "",
        "The threshold is tuned on the same questions it is scored on, so these numbers are "
        "optimistic. Questions the gate lets through can still be refused by the model, which is "
        "told to reply NOT_FOUND when the passages don't hold the answer (see below).",
    ]
    if report.get("answers"):
        a = report["answers"]
        lines += [
            "",
            f"## End-to-end answers ({s['llm_model']}, hybrid search)",
            "",
            "| Measure | Result | Proposal target |",
            "| --- | --- | --- |",
            f"| Answerable questions answered | {pct(a['answered_rate'])} | |",
            f"| Unanswerable questions refused | {pct(a['refusal_recall'])} | |",
            f"| Answers citing the expected document | {pct(a['cites_expected_doc'])} | |",
            f"| Answer time, p50 / p95 | {a['answer_p50_ms'] / 1000:.1f} s / "
            f"{a['answer_p95_ms'] / 1000:.1f} s | 5 to 10 s |",
            f"| First words on screen, p50 | {a['first_token_p50_ms'] / 1000:.1f} s | |",
            "",
            "Faithfulness (target: at least 90% of sampled answers supported by the cited "
            "passage) is checked by hand in `eval/review/faithfulness.csv`; summary and tag "
            "quality (target: 4 out of 5) in `eval/review/summaries.csv`.",
        ]
    return "\n".join(lines) + "\n"


# --- main ----------------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--llm", action="store_true", help="also answer with Gemini (needs key)")
    parser.add_argument(
        "--min-recall", type=float, default=None, help="exit 1 if hybrid source recall@3 < this"
    )
    parser.add_argument("--out", type=Path, default=HERE / "results.md")
    args = parser.parse_args()

    from app.db import SessionLocal
    from app.services.embeddings import get_embedder
    from app.services.llm import get_llm
    from app.services.search import SearchMode

    settings = get_settings()
    questions = load_questions()
    prepare_database()
    embedder = get_embedder()
    llm = get_llm() if args.llm else None

    with SessionLocal() as session:
        print("Loading the corpus...", flush=True)
        item_doc, setup = ingest(session, embedder, llm)
        print(f"  {setup['documents']} documents, {setup['chunks']} chunks", flush=True)
        embedder.embed_query("warm up")  # keep model start-up out of the latency numbers

        report: dict = {"retrieval": {}}
        for mode in SearchMode:
            result = evaluate_retrieval(session, embedder, questions, item_doc, mode)
            report["retrieval"][mode.value] = {
                "all": retrieval_metrics(result, questions),
                "paraphrase": retrieval_metrics(result, questions, "paraphrase"),
                "keyword": retrieval_metrics(result, questions, "keyword"),
                "p50_ms": percentile(result.latencies_ms, 50),
                "p95_ms": percentile(result.latencies_ms, 95),
                "misses": sorted(i for i, r in result.ranks.items() if not r or r > 3),
            }
            m = report["retrieval"][mode.value]["all"]
            print(
                f"  {mode.value:8} source@3 {pct(m['recall@3'])}  passage@1 {pct(m['passage@1'])}"
                f"  passage@3 {pct(m['passage@3'])}  in context {pct(m['answer_in_context'])}"
            )

        sims = best_similarities(session, embedder, questions)
        sweep = gate_sweep(sims, questions)
        configured = min(sweep, key=lambda r: abs(r["threshold"] - settings.min_similarity))
        report["gate"] = {
            "best": pick_threshold(sweep),
            "configured": configured,
            "answerable_min": min(sims[q.id] for q in questions if q.doc),
            "answerable_max": max(sims[q.id] for q in questions if q.doc),
            "unanswerable_min": min(sims[q.id] for q in questions if not q.doc),
            "unanswerable_max": max(sims[q.id] for q in questions if not q.doc),
            "similarities": sims,
            "sweep": sweep,
        }

        if llm is not None:
            print("Answering every question with the LLM...", flush=True)
            rows = evaluate_answers(session, embedder, llm, questions, item_doc)
            report["answers"] = answer_metrics(rows)
            report["answer_rows"] = rows
            write_review_sheets(rows, session)

    report["setup"] = {
        **setup,
        "generated": datetime.now(UTC).strftime("%Y-%m-%d"),
        "commit": git_commit(),
        "answerable": sum(q.doc is not None for q in questions),
        "unanswerable": sum(q.doc is None for q in questions),
        "embedding_model": settings.embedding_model,
        "llm_model": settings.gemini_model,
        "chunk_tokens": settings.chunk_tokens,
        "answer_k": settings.answer_k,
    }
    args.out.write_text(render(report))
    args.out.with_suffix(".json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(f"Wrote {args.out}", flush=True)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(render(report))

    recall = report["retrieval"]["hybrid"]["all"]["recall@3"]
    if args.min_recall is not None and recall < args.min_recall:
        print(f"Hybrid recall@3 {pct(recall)} is below the {pct(args.min_recall)} floor")
        sys.exit(1)


if __name__ == "__main__":
    main()
