"""Copy the local demo library into a hosted database: uv run python -m demo.publish TARGET_URL

The deployed app gives visitors copies of this library (app/services/guest.py), so it has to
be in the deployed database. This copies the local demo database's rows (built by demo.seed;
DEMO_DATABASE_URL, default recall_demo) into TARGET_URL with pg_dump, then moves the
pictures and PDFs from local disk into the database itself, since free hosts wipe their disk.

TARGET_URL must have no accounts yet: this sets up an empty database, it doesn't merge. Then
set GUEST_TEMPLATE_EMAIL=demo@example.com on the API. Needs pg_dump and psql (Postgres 17).
"""

import argparse
import os
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text

from demo.seed import DEFAULT_DB, EMAIL

# Not copied: sign-ins, tokens, background jobs and today's LLM count belong to this machine.
SKIP = ["alembic_version", "user_sessions", "api_tokens", "jobs", "llm_calls"]


def libpq(url: str) -> str:
    """postgresql+psycopg://... (SQLAlchemy) to postgresql://... (pg_dump and psql)."""
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def sqlalchemy(url: str) -> str:
    return url.replace("postgresql://", "postgresql+psycopg://", 1).replace(
        "postgres://", "postgresql+psycopg://", 1
    )


def migrate(url: str) -> None:
    from alembic.config import Config

    from alembic import command

    os.environ["DATABASE_URL"] = url
    here = os.path.dirname(__file__)
    cfg = Config(os.path.join(here, "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(here, "..", "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", help="the hosted database's URL (Neon's connection string)")
    args = parser.parse_args()
    source = os.environ.get("DEMO_DATABASE_URL", DEFAULT_DB)
    target = sqlalchemy(args.target)

    engine = create_engine(target)
    with engine.connect() as conn:
        has_users = conn.scalar(
            text("SELECT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'users')")
        ) and conn.scalar(text("SELECT EXISTS (SELECT 1 FROM users)"))
    if has_users:
        sys.exit("The target already has accounts; this only fills an empty database.")

    print("Creating the tables…", flush=True)
    migrate(target)

    print("Copying the demo library…", flush=True)
    dump = ["pg_dump", "--data-only", "--no-owner", "--no-privileges", libpq(source)]
    dump += [f"--exclude-table-data={t}" for t in SKIP]
    dumped = subprocess.run(dump, capture_output=True, check=True).stdout
    subprocess.run(
        ["psql", "--quiet", "--output", os.devnull, "--set", "ON_ERROR_STOP=1", libpq(target)],
        input=dumped,
        check=True,
    )

    print("Moving files into the database…", flush=True)
    backend = Path(__file__).resolve().parent.parent
    moved = 0
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT 'items', id, source FROM items WHERE source_type IN ('pdf', 'file') "
                "AND source NOT LIKE 'db:%' UNION ALL "
                "SELECT 'pages', id, pages_file FROM items WHERE pages_file NOT LIKE 'db:%' "
                "UNION ALL SELECT 'item_images', id, key FROM item_images WHERE key NOT LIKE 'db:%'"
            )
        ).all()
        for table, row_id, key in rows:
            path = Path(key) if Path(key).is_absolute() else backend / key
            if not path.is_file():
                print(f"  missing on disk, left as is: {key}")
                continue
            new_key = f"db:{uuid.uuid4().hex}{path.suffix.lower()}"
            conn.execute(
                text("INSERT INTO stored_files (key, data) VALUES (:key, :data)"),
                {"key": new_key, "data": path.read_bytes()},
            )
            table, column = {
                "items": ("items", "source"),
                "pages": ("items", "pages_file"),
                "item_images": ("item_images", "key"),
            }[table]
            conn.execute(
                text(f"UPDATE {table} SET {column} = :key WHERE id = :id"),
                {"key": new_key, "id": row_id},
            )
            moved += 1
        items = conn.scalar(text("SELECT count(*) FROM items"))
    print(f"Done: {items} items, {moved} files. On the API, set GUEST_TEMPLATE_EMAIL={EMAIL}")


if __name__ == "__main__":
    main()
