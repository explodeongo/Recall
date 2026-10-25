"""Turns a saved item into chunks, embeddings, a summary and tags.

Filled in during milestone 2 (ingest and process).
"""

from sqlalchemy.orm import Session

from app.models import Item


class PermanentError(Exception):
    """A failure that retrying will not fix, such as a scanned PDF with no text layer."""


def process_item(session: Session, item: Item) -> None:
    raise NotImplementedError("Processing pipeline lands in milestone 2")
