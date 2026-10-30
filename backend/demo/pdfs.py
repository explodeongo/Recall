"""Keep the demo's PDFs as files: uv run python -m demo.pdfs [TARGET_URL]

The Read tab shows a PDF's pages only when Recall has the file. This fills in what the demo
library was built without:

- Linked PDFs (the Attention paper, saved as an arXiv link): downloaded, stored, and the item
  made an uploaded PDF.
- Wikipedia articles: Wikipedia's printable PDF of each, kept beside the page (`pages_file`),
  as Recall now does whenever a Wikipedia link is saved.

Text, passages, summaries and everything made from them stay as they are. Visitors who start
the demo afterwards get the PDFs; copies made before don't.

TARGET_URL is the hosted database (Neon's connection string); without it, the local demo
database (DEMO_DATABASE_URL, default recall_demo). Safe to run again: items that already have
their PDF are skipped.
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


def _store(conn, data: bytes) -> str:
    key = f"db:{uuid.uuid4().hex}.pdf"
    conn.execute(
        text("INSERT INTO stored_files (key, data) VALUES (:key, :data)"),
        {"key": key, "data": data},
    )
    return key


def keep_pdfs(url: str) -> int:
    """Store the demo's linked PDFs and Wikipedia articles' PDFs. Returns how many."""
    from app.sources import wikipedia
    from app.sources.url import user_agent

    url = url.replace("postgresql://", "postgresql+psycopg://", 1).replace(
        "postgres://", "postgresql+psycopg://", 1
    )
    engine = create_engine(url)
    with engine.connect() as conn:
        items = conn.execute(
            text(
                "SELECT i.id, i.title, i.source FROM items i JOIN users u ON u.id = i.user_id "
                "WHERE u.email = :email AND i.source_type = 'url' AND i.pages_file IS NULL "
                "ORDER BY i.id"
            ),
            {"email": EMAIL},
        ).all()
    stored = 0
    with httpx.Client(
        timeout=60, follow_redirects=True, headers={"User-Agent": user_agent()}
    ) as client:
        for item_id, title, link in items:
            # One item at a time, so an interrupted run keeps what it stored.
            if PDF_LINK.search(link.split("?")[0]):
                resp = client.get(link)
                resp.raise_for_status()
                if not resp.content.startswith(b"%PDF-"):
                    print(f"  not a PDF, left as a link: {title}")
                    continue
                with engine.begin() as conn:
                    conn.execute(
                        text("UPDATE items SET source_type = 'pdf', source = :key WHERE id = :id"),
                        {"key": _store(conn, resp.content), "id": item_id},
                    )
                size = len(resp.content)
            elif wikipedia.pdf_url(link):
                data = wikipedia.fetch_pdf(link)
                if data is None:
                    print(f"  Wikipedia had no PDF for {title}")
                    continue
                with engine.begin() as conn:
                    conn.execute(
                        text("UPDATE items SET pages_file = :key WHERE id = :id"),
                        {"key": _store(conn, data), "id": item_id},
                    )
                size = len(data)
            else:
                continue
            print(f"  stored {title} ({size // 1024} KB)")
            stored += 1
    engine.dispose()
    return stored


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", nargs="?", help="the hosted database's URL (default: local)")
    args = parser.parse_args()
    url = args.target or os.environ.get("DEMO_DATABASE_URL", DEFAULT_DB)
    if not keep_pdfs(url):
        sys.exit("Nothing to store: the demo's PDFs are already kept.")
    print("Done. New demo visitors get the PDFs.")


if __name__ == "__main__":
    main()
