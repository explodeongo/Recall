import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://recall:recall@localhost:5432/recall_test"
)

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Item, SourceType  # noqa: E402
from app.pipeline import process_item  # noqa: E402
from app.services.embeddings import HashingEmbedder  # noqa: E402
from app.sources import ExtractedDoc, PageText  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE items, tags, jobs, chats RESTART IDENTITY CASCADE"))


@pytest.fixture
def session():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def fake_llm():
    from tests.helpers import FakeLLM

    return FakeLLM()


@pytest.fixture
def client(tmp_path, monkeypatch, fake_llm):
    from app.config import get_settings
    from app.deps import embedder_dep, llm_dep
    from app.services.embeddings import HashingEmbedder

    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    app.dependency_overrides[embedder_dep] = HashingEmbedder
    app.dependency_overrides[llm_dep] = lambda: fake_llm
    yield TestClient(app)
    app.dependency_overrides.clear()


LIBRARY = {
    "Database indexing": [
        "A hash index maps keys to buckets, so exact-match lookups are very fast.",
        "A B-tree keeps keys sorted, so it also serves range scans and ORDER BY queries.",
    ],
    "Transformers": [
        "The transformer architecture relies on self-attention instead of recurrence.",
        "Positional encodings tell the model the order of the tokens in a sequence.",
    ],
    "Sourdough baking": [
        "A sourdough starter is a culture of wild yeast and lactobacilli.",
        "Bulk fermentation at warm temperatures makes the dough rise faster.",
    ],
}


class StubSource:
    def __init__(self, pages):
        self.pages = pages

    def extract(self, item):
        return ExtractedDoc(title=None, pages=self.pages)


@pytest.fixture
def library(session, monkeypatch):
    # Small chunks without overlap: one chunk per page, so a citation's page can be checked.
    monkeypatch.setattr(get_settings(), "chunk_tokens", 20)
    monkeypatch.setattr(get_settings(), "chunk_overlap", 0)
    # The hashing embedder's similarities run lower than bge's; questions sharing a few words
    # with a passage score about 0.3, unrelated ones 0.
    monkeypatch.setattr(get_settings(), "min_similarity", 0.2)
    ids = {}
    for title, pages in LIBRARY.items():
        item = Item(title=title, source_type=SourceType.pdf, source="unused")
        session.add(item)
        session.flush()
        pages = [PageText(i + 1, text) for i, text in enumerate(pages)]
        process_item(session, item, embedder=HashingEmbedder(), llm=None, source=StubSource(pages))
        ids[title] = item.id
    session.commit()
    return ids
