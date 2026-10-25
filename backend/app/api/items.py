import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import HttpUrl, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.deps import SessionDep
from app.models import Item, ItemStatus, SourceType, Tag
from app.schemas import ItemOut
from app.services import jobs

router = APIRouter(prefix="/items", tags=["items"])
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
    """One item's summary, tags, status and source (FR-7)."""
    return _get_or_404(session, item_id)


@router.get("/{item_id}/file", response_class=FileResponse)
def get_item_file(item_id: int, session: SessionDep) -> FileResponse:
    """The original PDF, so a citation can open it at the cited page (`#page=N`)."""
    item = _get_or_404(session, item_id)
    path = Path(item.source)
    if item.source_type != SourceType.pdf or not path.exists():
        raise HTTPException(404, "This item has no stored file")
    filename = f"{item.title[:100]}.pdf".replace('"', "")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=filename,
        content_disposition_type="inline",
    )


@router.post("/{item_id}/reprocess", response_model=ItemOut, status_code=202)
def reprocess_item(item_id: int, session: SessionDep) -> Item:
    """Queue an item to be processed again, for example after a failure."""
    item = _get_or_404(session, item_id)
    if item.status in (ItemStatus.queued, ItemStatus.processing):
        raise HTTPException(409, "This item is already being processed")
    jobs.enqueue(session, item)
    session.commit()
    return item


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, session: SessionDep) -> Response:
    item = _get_or_404(session, item_id)
    stored = Path(item.source) if item.source_type == SourceType.pdf else None
    session.delete(item)
    session.commit()
    if stored is not None:
        stored.unlink(missing_ok=True)
    return Response(status_code=204)


def _get_or_404(session, item_id: int) -> Item:
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
