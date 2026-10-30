"""Keep the demo's linked PDFs as files: uv run python -m demo.pdfs [TARGET_URL]

The demo saved the Attention paper as an arXiv link, so Recall read its text but kept no file,
and the Read tab could only show that text. This downloads each linked PDF in the demo
account's library, stores it in the database, and makes the item an uploaded PDF, so the Read
tab shows its pages. Its text, passages, summary and everything made from them stay as they
are. Visitors who start the demo afterwards get the PDF; copies made before keep the link.

TARGET_URL is the hosted database (Neon's connection string); without it, the local demo
database (DEMO_DATABASE_URL, default recall_demo). Safe to run again: items already stored as
PDFs are skipped.
"""

import argparse
import os
import re
import sys
import uuid

import httpx
from sqlalchemy import create_engine, text

from demo.seed import DEFAULT_DB, EMAIL

# Links that serve a PDF rather than a page.
PDF_LINK = re.compile(r"(\.pdf$|/pdf/)", re.IGNORECASE)


def keep_pdfs(url: str) -> int:
    """Store the demo's linked PDFs and make those items uploaded PDFs. Returns how many."""
    from app.sources.url import user_agent

    url = url.replace("postgresql://", "postgresql+psycopg://", 1).replace(
        "postgres://", "postgresql+psycopg://", 1
    )
    engine = create_engine(url)
    stored = 0
    with (
        engine.begin() as conn,
        httpx.Client(
            timeout=60, follow_redirects=True, headers={"User-Agent": user_agent()}
        ) as client,
    ):
        items = conn.execute(
            text(
                "SELECT i.id, i.title, i.source FROM items i JOIN users u ON u.id = i.user_id "
                "WHERE u.email = :email AND i.source_type = 'url'"
            ),
            {"email": EMAIL},
        ).all()
        for item_id, title, link in items:
            if not PDF_LINK.search(link.split("?")[0]):
                continue
            resp = client.get(link)
            resp.raise_for_status()
            if not resp.content.startswith(b"%PDF-"):
                print(f"  not a PDF, left as a link: {title}")
                continue
            key = f"db:{uuid.uuid4().hex}.pdf"
            conn.execute(
                text("INSERT INTO stored_files (key, data) VALUES (:key, :data)"),
                {"key": key, "data": resp.content},
            )
            conn.execute(
                text("UPDATE items SET source_type = 'pdf', source = :key WHERE id = :id"),
                {"key": key, "id": item_id},
            )
            print(f"  stored {title} ({len(resp.content) // 1024} KB)")
            stored += 1
    engine.dispose()
    return stored


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", nargs="?", help="the hosted database's URL (default: local)")
    args = parser.parse_args()
    url = args.target or os.environ.get("DEMO_DATABASE_URL", DEFAULT_DB)
    if not keep_pdfs(url):
        sys.exit("No linked PDFs to store: the demo's PDFs are already files.")
    print("Done. New demo visitors get the PDFs.")


if __name__ == "__main__":
    main()
