import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import HttpUrl, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db import get_session
from app.models import Item, SourceType, Tag
from app.schemas import ItemOut
from app.services import jobs

router = APIRouter(prefix="/items", tags=["items"])

SessionDep = Annotated[Session, Depends(get_session)]
_url_adapter = TypeAdapter(HttpUrl)


@router.post("", response_model=ItemOut, status_code=status.HTTP_202_ACCEPTED)
def create_item(
    session: SessionDep,
    file: Annotated[UploadFile | None, File()] = None,
    url: Annotated[str | None, Form()] = None,
) -> Item:
    """Save a PDF upload or a web-article URL (FR-1). Processing runs in the background."""
    if (file is None) == (url is None):
        raise HTTPException(422, "Send exactly one of: a PDF file, or a url")

    if file is not None:
        item = Item(
            title=_title_from_filename(file.filename), source_type=SourceType.pdf, source=""
        )
        item.source = _store_pdf(file)
    else:
        try:
            clean = str(_url_adapter.validate_python(url))
        except ValidationError as exc:
            raise HTTPException(422, "That doesn't look like a valid http(s) URL") from exc
        item = Item(title=clean, source_type=SourceType.url, source=clean)

    session.add(item)
    session.flush()
    jobs.enqueue(session, item)
    session.commit()
    session.refresh(item, ["tags"])
    return item


@router.get("", response_model=list[ItemOut])
def list_items(session: SessionDep, tag: str | None = None) -> list[Item]:
    """List items, newest first, optionally filtered by tag name (FR-6). No LLM involved."""
    query = select(Item).options(selectinload(Item.tags)).order_by(Item.created_at.desc())
    if tag:
        query = query.where(Item.tags.any(Tag.name == tag.lower()))
    return list(session.scalars(query))


@router.get("/{item_id}", response_model=ItemOut)
def get_item(item_id: int, session: SessionDep) -> Item:
    item = session.get(Item, item_id, options=[selectinload(Item.tags)])
    if item is None:
        raise HTTPException(404, "Item not found")
    return item


def _title_from_filename(name: str | None) -> str:
    stem = Path(name or "Untitled").stem.replace("_", " ").strip()
    return stem or "Untitled"


def _store_pdf(file: UploadFile) -> str:
    settings = get_settings()
    head = file.file.read(5)
    if head != b"%PDF-":
        raise HTTPException(415, "Only PDF files are supported")
    limit = settings.max_upload_mb * 1024 * 1024
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{uuid.uuid4().hex}.pdf"
    size = len(head)
    with dest.open("wb") as out:
        out.write(head)
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"PDF is larger than {settings.max_upload_mb} MB")
            out.write(chunk)
    return str(dest)
