"""The evaluation set is only meaningful if its answers really are in the corpus."""

import json
from pathlib import Path

EVAL = Path(__file__).parent.parent / "eval"
CORPUS = {p.stem: p.read_text() for p in (EVAL / "corpus").glob("*.txt")}
QUESTIONS = [json.loads(line) for line in (EVAL / "questions.jsonl").read_text().splitlines()]


def test_manifest_matches_corpus_files():
    manifest = json.loads((EVAL / "corpus.json").read_text())
    assert {d["id"] for d in manifest} == set(CORPUS)
    assert all(d["license"] and d["revision_url"] for d in manifest)


def test_every_answer_is_in_its_document():
    for q in QUESTIONS:
        if q["doc"] is not None:
            assert q["answer"].lower() in CORPUS[q["doc"]].lower(), q["id"]


def test_ids_are_unique_and_the_set_is_big_enough():
    ids = [q["id"] for q in QUESTIONS]
    assert len(ids) == len(set(ids))
    assert sum(q["doc"] is not None for q in QUESTIONS) >= 30
    assert sum(q["doc"] is None for q in QUESTIONS) >= 8
