"""Build the demo library: uv run python -m demo.seed [--fresh]

Loads about 30 real sources (Wikipedia articles, the Attention paper, two YouTube lectures)
and three notes into DEMO_DATABASE_URL (default: a local recall_demo database; anything not
ending in _demo is refused), under a local demo account. Every item goes through the real
pipeline: pages are fetched, Gemini writes summaries and tags, embeddings are made locally.
Then it adds what a few weeks of use leaves behind: notes, highlights, starred items, a tag
made by hand, chats with follow-ups, and quizzes with a few reviews. Saved dates are spread
over the past six weeks so the library looks lived in and "Worth another look" has
something to offer.

Run the app on it with ./dev.sh --demo and log in as demo@example.com / recall-demo.
--fresh drops the demo database and starts again. Needs GEMINI_API_KEY and the internet;
takes 5 to 10 minutes, mostly waiting for the free Gemini tier.
"""

import argparse
import os
import sys
import time
from datetime import UTC, datetime, timedelta

DEFAULT_DB = "postgresql+psycopg://recall:recall@localhost:5432/recall_demo"
os.environ["DATABASE_URL"] = os.environ.get("DEMO_DATABASE_URL", DEFAULT_DB)
os.environ.setdefault("UPLOAD_DIR", "data/demo-uploads")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

EMAIL = "demo@example.com"
PASSWORD = "recall-demo"  # a local demo account, not a secret

WIKI = "https://en.wikipedia.org/wiki/"
# (source, days ago it was "saved"). Grouped by topic; saved in reading order.
SOURCES: list[tuple[str | dict, int]] = [
    # How AI models read and write
    ("https://arxiv.org/pdf/1706.03762", 40),
    (WIKI + "Transformer_(deep_learning_architecture)", 39),
    (WIKI + "Attention_(machine_learning)", 38),
    ("https://www.youtube.com/watch?v=wjZofJX0v4M", 37),
    ("https://www.youtube.com/watch?v=kCc8FmEb1nY", 30),
    (WIKI + "Word_embedding", 29),
    (WIKI + "Large_language_model", 12),
    (WIKI + "Retrieval-augmented_generation", 3),
    # Search and databases
    (WIKI + "B-tree", 33),
    (WIKI + "Database_index", 33),
    (WIKI + "Inverted_index", 26),
    (WIKI + "Tf%E2%80%93idf", 25),
    (WIKI + "Okapi_BM25", 25),
    (WIKI + "Nearest_neighbor_search", 18),
    (WIKI + "Hierarchical_navigable_small_world", 17),
    (WIKI + "Vector_database", 16),
    # Learning and memory
    (WIKI + "Forgetting_curve", 22),
    (WIKI + "Spacing_effect", 22),
    (WIKI + "Spaced_repetition", 21),
    (WIKI + "Testing_effect", 20),
    (WIKI + "Zettelkasten", 9),
    (WIKI + "Personal_knowledge_management", 8),
    # Building products
    (WIKI + "Minimum_viable_product", 28),
    (WIKI + "Lean_startup", 27),
    (WIKI + "A/B_testing", 14),
    (WIKI + "Product_management", 6),
    # The reader's own notes
    (
        {
            "title": "Reading plan: how search actually works",
            "text": "I want to understand how search engines and vector databases find "
            "things. Start with inverted indexes and BM25, then embeddings and approximate "
            "nearest neighbour search (HNSW). The question to answer: when is keyword "
            "search better than semantic search, and why do hybrid systems combine both? "
            "Recall itself uses reciprocal rank fusion of the two, so this matters for the "
            "project report.",
        },
        19,
    ),
    (
        {
            "title": "Why I forget what I read",
            "text": "Noticed I can't explain most papers a month after reading them. The "
            "forgetting curve says most of it goes within days unless it's reviewed. "
            "Plan: quiz myself on anything worth keeping, a few minutes a day, and let the "
            "spacing grow. Testing beats rereading, so questions rather than highlights.",
        },
        20,
    ),
    (
        {
            "title": "Explaining transformers in an interview",
            "text": "Short version: a transformer reads all the words at once and lets each "
            "word look at every other word (self-attention) to decide what matters. "
            "Positional encodings keep the order. Stacking these layers is what large "
            "language models are made of. Follow-up to prepare: why attention scales "
            "quadratically with sequence length.",
        },
        5,
    ),
]

TO_READ = {"title_has": ["Retrieval-augmented", "Vector database", "Product management"]}
STARRED = ["Attention Is All You Need", "Spaced repetition", "BM25"]
HIGHLIGHTS = [
    ("Forgetting curve", "exponential", "This is why reviewing within a day matters so much."),
    ("Okapi BM25", "term frequency", "BM25 caps how much repeating a word can help."),
    ("Attention Is All You Need", "Scaled Dot-Product Attention", None),
]
ITEM_NOTES = [
    (
        "Spacing effect",
        "Same total study time, better retention, just spread out. Applies to interview prep too.",
    ),
    (
        "Minimum viable product",
        "Recall's first version was: save a PDF, ask a question, get a "
        "cited answer. Everything else came after.",
    ),
]
QUIZZES = ["Attention Is All You Need", "Spaced repetition", "B-tree"]
CHATS = [
    {
        "questions": [
            "How does BM25 decide which documents rank highest?",
            "How is that different from how a vector database finds matches?",
        ],
    },
    {"questions": ["Why does spacing out reviews help me remember more?"]},
    {
        "pin": "Attention Is All You Need",
        "questions": ["What problem does self-attention solve compared to recurrence?"],
    },
    # Nothing saved compares the two head on, so this one is answered from the web, labelled.
    {"questions": ["When is keyword search better than semantic search?"]},
]


def prepare_database(fresh: bool) -> None:
    url = make_url(os.environ["DATABASE_URL"])
    if not url.database or not url.database.endswith("_demo"):
        sys.exit(f"Refusing to build the demo in '{url.database}': use a *_demo database")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
        )
        if exists and fresh:
            conn.execute(text(f'DROP DATABASE "{url.database}" WITH (FORCE)'))
            exists = False
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()

    from alembic.config import Config

    from alembic import command

    here = os.path.dirname(__file__)
    cfg = Config(os.path.join(here, "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(here, "..", "alembic"))
    command.upgrade(cfg, "head")


def say(message: str) -> None:
    print(f"\033[1m{message}\033[0m", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fresh", action="store_true", help="drop and rebuild the demo database")
    args = parser.parse_args()

    prepare_database(args.fresh)

    from fastapi.testclient import TestClient

    from app.db import SessionLocal
    from app.main import app

    client = TestClient(app)
    if client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code != 200:
        resp = client.post(
            "/auth/signup", json={"email": EMAIL, "password": PASSWORD, "name": "Aryan"}
        )
        resp.raise_for_status()
    if client.get("/items").json():
        sys.exit("The demo library already has items. Use --fresh to rebuild it.")

    say(f"Saving {len(SOURCES)} items…")
    saved: list[tuple[int, int]] = []
    for source, days in SOURCES:
        data = {"url": source} if isinstance(source, str) else source
        resp = client.post("/items", data=data)
        resp.raise_for_status()
        saved.append((resp.json()["id"], days))

    read_everything(SessionLocal)
    backdate(SessionLocal, saved)
    drop_failed(client)

    items = {i["title"]: i for i in client.get("/items").json()}
    say(f"{len(items)} items ready. Adding notes, highlights, stars and tags…")
    use_the_library(client, items)
    say("Asking a few questions…")
    for chat in CHATS:
        ask(client, items, chat)
    say("Making quizzes…")
    quiz(client, items)
    say("Done. Run ./dev.sh --demo and log in as demo@example.com / recall-demo")


def read_everything(SessionLocal) -> None:
    """Run the worker until every item is read (or has failed for good)."""
    from sqlalchemy import func, select

    from app.models import Item, ItemStatus
    from app.services.embeddings import get_embedder
    from app.worker import run_once

    embedder = get_embedder()
    started = time.monotonic()
    while time.monotonic() - started < 30 * 60:
        if run_once(embedder):
            with SessionLocal() as s:
                done = s.scalar(
                    select(func.count(Item.id)).where(
                        Item.status.in_([ItemStatus.ready, ItemStatus.failed])
                    )
                )
                total = s.scalar(select(func.count(Item.id)))
            print(f"  read {done}/{total}", flush=True)
            continue
        with SessionLocal() as s:
            busy = s.scalar(
                select(func.count(Item.id)).where(
                    Item.status.in_([ItemStatus.queued, ItemStatus.processing])
                )
            )
        if not busy:
            return
        time.sleep(3)  # retries wait out the free tier's rate limit
    sys.exit("Gave up after 30 minutes; run again with --fresh later.")


def backdate(SessionLocal, saved: list[tuple[int, int]]) -> None:
    """Spread the saved dates over the past weeks, as a real library would be."""
    now = datetime.now(UTC)
    with SessionLocal() as s:
        for n, (item_id, days) in enumerate(saved):
            when = now - timedelta(days=days, hours=9 - n % 9, minutes=n * 7)
            s.execute(
                text("UPDATE items SET created_at = :when WHERE id = :id"),
                {"when": when, "id": item_id},
            )
        s.commit()


def drop_failed(client) -> None:
    for item in client.get("/items").json():
        if item["status"] == "failed":
            print(f"  couldn't read {item['source']}: {item['error']} (left out)")
            client.delete(f"/items/{item['id']}")


def find(items: dict, fragment: str) -> dict | None:
    return next((i for t, i in items.items() if fragment.lower() in t.lower()), None)


def use_the_library(client, items: dict) -> None:
    for name in STARRED:
        if item := find(items, name):
            client.patch(f"/items/{item['id']}", json={"starred": True})

    client.post("/tags", json={"name": "to read", "color": "#e5484d"})
    for name in TO_READ["title_has"]:
        if item := find(items, name):
            names = [t["name"] for t in item["tags"]] + ["to read"]
            client.put(f"/items/{item['id']}/tags", json={"tags": names})

    for name, note in ITEM_NOTES:
        if item := find(items, name):
            client.put(f"/items/{item['id']}/note", json={"note": note + picture_for(client, item)})

    for name, phrase, note in HIGHLIGHTS:
        item = find(items, name)
        if item is None:
            continue
        pages = client.get(f"/items/{item['id']}/content").json()["pages"]
        body = "\n\n".join(p["text"] for p in pages)
        at = body.lower().find(phrase.lower())
        if at == -1:
            continue
        start = max(body.rfind(". ", 0, at) + 2, body.rfind("\n", 0, at) + 1, 0)
        end = body.find(". ", at)
        end = len(body) if end == -1 else end + 1
        if end - start > 600:
            start, end = at, min(len(body), at + 300)
        client.post(
            f"/items/{item['id']}/highlights",
            json={"start_char": start, "end_char": end, "note": note},
        )

    # Open the newer half, so the older unopened ones come back as "Worth another look".
    for item in sorted(items.values(), key=lambda i: i["created_at"])[len(items) // 2 :]:
        client.post(f"/items/{item['id']}/opened")


def with_retries(attempt, what: str, tries: int = 4) -> bool:
    """Run `attempt` until it succeeds; the free Gemini tier is often briefly overloaded."""
    for n in range(tries):
        if attempt():
            return True
        time.sleep(15 * (n + 1))
    print(f"  gave up on {what}; run `python -m demo.seed --fresh` again later")
    return False


def picture_for(client, item: dict) -> str:
    """For the note on "Spacing effect": the forgetting-curve graph from its article, added
    the way a reader pastes a picture into a note. Empty for other notes."""
    if "spacing" not in item["title"].lower():
        return ""
    curve = next(
        (i for i in client.get("/items").json() if "forgetting" in i["title"].lower()), None
    )
    if curve is None:
        return ""
    figures = client.get(f"/items/{curve['id']}/content").json().get("images", [])
    if not figures:
        return ""
    data = client.get(f"/images/{figures[0]['id']}").content
    made = client.post(
        "/images",
        files={"file": ("forgetting-curve.jpg", data, "image/jpeg")},
        data={"item_id": str(item["id"]), "alt": "The forgetting curve"},
    )
    if made.status_code != 201:
        return ""
    return f"\n\n![The forgetting curve](image:{made.json()['id']})"


def ask(client, items: dict, chat: dict) -> None:
    chat_id = client.post("/chats", json={}).json()["id"]
    pinned = find(items, chat["pin"]) if chat.get("pin") else None
    for question in chat["questions"]:
        body = {"question": question, "source": "both"}
        if pinned:
            body |= {"item_ids": [pinned["id"]], "source": "library"}

        def attempt(body=body) -> bool:
            resp = client.post(f"/chats/{chat_id}/messages", json=body)
            return "event: done" in resp.text

        if not with_retries(attempt, f"“{question}”"):
            return  # a follow-up without its question would read oddly
        time.sleep(4)  # stay under the free tier's per-minute limit


def quiz(client, items: dict) -> None:
    for name in QUIZZES:
        item = find(items, name)
        if item is None:
            continue
        made: list = []

        def attempt(item=item, made=made) -> bool:
            resp = client.post(f"/items/{item['id']}/cards")
            made[:] = resp.json() if resp.status_code == 201 else []
            return resp.status_code == 201

        if not with_retries(attempt, f"the quiz for {name}"):
            continue
        # A few already reviewed, so cards show more than one stage.
        for card in made[:3]:
            client.post(f"/cards/{card['id']}/review", json={"grade": "good"})
        time.sleep(4)


if __name__ == "__main__":
    main()
