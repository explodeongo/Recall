"""Add a PDF to the demo library: uv run python -m demo.add FILE.pdf [TARGET_URL]

Saves the PDF to the demo account and reads it with the real pipeline, here on this machine
(text, passages, embeddings, and Gemini's summary and tags), straight into the database, so a
hosted demo gets a new item without being rebuilt. Visitors who start the demo afterwards get
it; copies made before don't.

TARGET_URL is the hosted database (Neon's connection string); without it, the local demo
database (DEMO_DATABASE_URL, default recall_demo). Needs GEMINI_API_KEY. Adding the same file
twice is refused. --title names it, when the PDF's own title (or Gemini's) isn't the one to show.
"""

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from demo.seed import DEFAULT_DB, EMAIL  # sets DATABASE_URL, so the target is set after it

DAYS_AGO = 2  # "Saved 2 days ago": recent, but not something the visitor just did


def add_pdf(path: Path, url: str, title: str | None = None) -> str:
    """Save and read `path` into the demo library at `url`. Returns the item's title."""
    os.environ["DATABASE_URL"] = url.replace("postgresql://", "postgresql+psycopg://", 1).replace(
        "postgres://", "postgresql+psycopg://", 1
    )
    # Hosted databases keep files in Postgres: their disks are wiped on restart.
    os.environ["FILE_STORE"] = "database"

    from sqlalchemy import select, text

    from app.db import SessionLocal
    from app.models import Item, ItemStatus, SourceType, User
    from app.pipeline import process_item
    from app.services import files
    from app.services.embeddings import get_embedder
    from app.services.llm import get_llm

    data = path.read_bytes()
    if not data.startswith(b"%PDF-"):
        sys.exit(f"{path.name} isn't a PDF.")
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == EMAIL))
        if user is None:
            sys.exit(f"No demo account ({EMAIL}) in that database.")
        same = session.scalar(
            text(
                "SELECT i.title FROM items i JOIN stored_files f ON f.key = i.source "
                "WHERE i.user_id = :user AND f.data = :data"
            ),
            {"user": user.id, "data": data},
        )
        if same:
            sys.exit(f"The demo library already has this file, as “{same}”.")

        key = files.save(data, ".pdf")
        try:
            item = Item(
                user_id=user.id,
                title=title or path.stem.replace("_", " "),
                title_edited=title is not None,
                source_type=SourceType.pdf,
                source=key,
                status=ItemStatus.processing,
            )
            session.add(item)
            session.flush()
            process_item(session, item, embedder=get_embedder(), llm=get_llm())
            item.status = ItemStatus.ready
            item.created_at = datetime.now(UTC) - timedelta(days=DAYS_AGO)
            session.commit()
            return item.title
        except BaseException:
            session.rollback()
            files.delete(key)
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("file", type=Path, help="the PDF to add")
    parser.add_argument("target", nargs="?", help="the hosted database's URL (default: local)")
    parser.add_argument("--title", help="the title to show (default: the PDF's own)")
    args = parser.parse_args()
    if not args.file.is_file():
        sys.exit(f"No such file: {args.file}")
    url = args.target or os.environ.get("DEMO_DATABASE_URL", DEFAULT_DB)
    title = add_pdf(args.file, url, args.title)
    print(f"Added “{title}”. New demo visitors get it.")


if __name__ == "__main__":
    main()
