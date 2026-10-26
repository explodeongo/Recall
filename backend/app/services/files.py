"""Where uploaded files live.

FILE_STORE=local (the default) keeps them in UPLOAD_DIR on disk. FILE_STORE=database keeps
them in Postgres, for hosts whose disk is wiped on every restart (most free tiers). The item's
`source` holds the key either way: a file path, or "db:<id><suffix>". Keys from either store
keep working if the setting changes later.
"""

import uuid
from pathlib import Path

from sqlalchemy import text

from app.config import get_settings
from app.db import engine

DB_PREFIX = "db:"


def save(data: bytes, suffix: str) -> str:
    settings = get_settings()
    if settings.file_store == "database":
        key = f"{DB_PREFIX}{uuid.uuid4().hex}{suffix}"
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO stored_files (key, data) VALUES (:key, :data)"),
                {"key": key, "data": data},
            )
        return key
    folder = Path(settings.upload_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}{suffix}"
    path.write_bytes(data)
    return str(path)


def read(key: str) -> bytes | None:
    if key.startswith(DB_PREFIX):
        with engine.connect() as conn:
            return conn.scalar(text("SELECT data FROM stored_files WHERE key = :key"), {"key": key})
    path = Path(key)
    return path.read_bytes() if path.is_file() else None


def delete(key: str) -> None:
    if key.startswith(DB_PREFIX):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM stored_files WHERE key = :key"), {"key": key})
    else:
        Path(key).unlink(missing_ok=True)


def suffix(key: str) -> str:
    return Path(key.removeprefix(DB_PREFIX)).suffix.lower()
