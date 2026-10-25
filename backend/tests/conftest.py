import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://recall:recall@localhost:5432/recall_test"
)

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


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
        conn.execute(text("TRUNCATE items, tags, jobs RESTART IDENTITY CASCADE"))


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
