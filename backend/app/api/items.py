import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import HttpUrl, TypeAdapter, ValidationError
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.deps import CurrentUser, EmbedderDep, SessionDep
from app.models import Card, Item, ItemStatus, SourceType, Tag, item_tags
from app.pipeline import get_or_create_tags
from app.schemas import ContentOut, ItemOut, ItemPatch, ResurfaceOut, TagsIn
from app.services import jobs
from app.services.enrich import clean_tag
from app.services.library_search import search_items
from app.sources.files import EXTENSIONS as FILE_EXTENSIONS
from app.sources.youtube import video_id

router = APIRouter(prefix="/items", tags=["items"])
RESURFACE_AFTER_DAYS = 7
MAX_NOTE_CHARS = 200_000
MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown; charset=utf-8",
    ".markdown": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}
_url_adapter = TypeAdapter(HttpUrl)


@router.post("", response_model=ItemOut, status_code=status.HTTP_202_ACCEPTED)
def create_item(
    session: SessionDep,
    user: CurrentUser,
    file: Annotated[UploadFile | None, File()] = None,
    url: Annotated[str | None, Form()] = None,
    text: Annotated[str | None, Form()] = None,
    title: Annotated[str | None, Form()] = None,
) -> Item:
    """Save something to the library (FR-1): a file (PDF, Word, Markdown or text), a link (an
    article, a PDF, or a YouTube video), or typed text as a note. It's read in the background."""
    if sum(x is not None for x in (file, url, text)) != 1:
        raise HTTPException(422, "Send exactly one of: a file, a url, or text")

    if file is not None:
        kind, path = _store_upload(file)
        name = title.strip() if title and title.strip() else _title_from_filename(file.filename)
        item = Item(user_id=user.id, title=name, source_type=kind, source=path)
    elif url is not None:
        try:
            clean = str(_url_adapter.validate_python(url.strip()))
        except ValidationError as exc:
            raise HTTPException(422, "That doesn't look like a valid http(s) URL") from exc
        kind = SourceType.youtube if video_id(clean) else SourceType.url
        item = Item(user_id=user.id, title=clean, source_type=kind, source=clean)
    else:
        body = text.strip()
        if not body:
            raise HTTPException(422, "The note is empty")
        if len(body) > MAX_NOTE_CHARS:
            raise HTTPException(413, f"Notes can be up to {MAX_NOTE_CHARS:,} characters")
        first_line = body.splitlines()[0].strip().lstrip("# ")
        name = title.strip() if title and title.strip() else first_line[:80] or "Note"
        item = Item(user_id=user.id, title=name, source_type=SourceType.note, source=body)

    session.add(item)
    session.flush()
    jobs.enqueue(session, item)
    session.commit()
    session.refresh(item, ["tags"])
    return item


@router.get("", response_model=list[ItemOut])
def list_items(
    session: SessionDep,
    user: CurrentUser,
    embedder: EmbedderDep,
    tag: str | None = None,
    q: str | None = None,
    view: Literal["all", "starred", "archived"] = "all",
) -> list[Item]:
    """List items, newest first (FR-6), or search them. `tag` filters by tag (no LLM). `q`
    matches each word anywhere: titles, tags, summaries, notes and full text, best first, with
    the matching passage; documents close in meaning follow as "related"
    (services/library_search.py)."""
    if q and q.strip():
        # Search covers everything, archived included: finding things is the point.
        return search_items(session, user.id, q, tag=tag, embedder=embedder)
    query = select(Item).where(Item.user_id == user.id).options(selectinload(Item.tags))
    if view == "starred":
        query = query.where(Item.starred.is_(True))
    query = query.where(Item.archived.is_(view == "archived"))
    if tag:
        query = query.where(Item.tags.any(Tag.name == tag.lower()))
    return list(session.scalars(query.order_by(Item.created_at.desc())))


@router.get("/resurface", response_model=ResurfaceOut)
def resurface(session: SessionDep, user: CurrentUser) -> dict:
    """A few things saved a while ago and not opened since, for the top of the library. The
    pick changes daily and skips anything opened or saved in the last few days."""
    stale = datetime.now(UTC) - timedelta(days=RESURFACE_AFTER_DAYS)
    seen = func.coalesce(Item.last_opened_at, Item.created_at)
    candidates = list(
        session.scalars(
            select(Item)
            .options(selectinload(Item.tags))
            .where(
                Item.user_id == user.id,
                Item.status == ItemStatus.ready,
                Item.archived.is_(False),
                seen < stale,
            )
            .order_by(seen, Item.id)
            .limit(30)
        )
    )
    # Rotate through the oldest-unseen items, a different few each day.
    if candidates:
        start = date.today().toordinal() % len(candidates)
        candidates = (candidates[start:] + candidates[:start])[:3]
    due = session.scalar(
        select(func.count(Card.id)).where(Card.user_id == user.id, Card.due_at <= func.now())
    )
    return {"items": candidates, "cards_due": due or 0}


@router.patch("/{item_id}", response_model=ItemOut)
def update_item(item_id: int, body: ItemPatch, session: SessionDep, user: CurrentUser) -> Item:
    """Rename, star or archive an item."""
    item = _get_or_404(session, item_id, user.id)
    if body.title is not None:
        item.title = body.title.strip()
    if body.starred is not None:
        item.starred = body.starred
    if body.archived is not None:
        item.archived = body.archived
    session.commit()
    session.refresh(item, ["tags"])
    return item


@router.post("/{item_id}/opened", status_code=204)
def mark_opened(item_id: int, session: SessionDep, user: CurrentUser) -> Response:
    """Called when the item page is opened, so resurfacing knows what's been looked at."""
    item = _get_or_404(session, item_id, user.id)
    item.last_opened_at = func.now()
    session.commit()
    return Response(status_code=204)


@router.get("/{item_id}", response_model=ItemOut)
def get_item(item_id: int, session: SessionDep, user: CurrentUser) -> Item:
    """One item's summary, tags, status and source (FR-7)."""
    return _get_or_404(session, item_id, user.id)


@router.get("/{item_id}/content", response_model=ContentOut)
def get_item_content(item_id: int, session: SessionDep, user: CurrentUser) -> ContentOut:
    """The cleaned full text, for reading inside Recall. Items saved before the reader existed
    have none until they're processed again."""
    item = _get_or_404(session, item_id, user.id)
    if item.content is None:
        raise HTTPException(
            404, "This item's text isn't stored yet. Process it again to read it here."
        )
    return ContentOut(pages=item.content)


@router.get("/{item_id}/file", response_class=FileResponse)
def get_item_file(item_id: int, session: SessionDep, user: CurrentUser) -> FileResponse:
    """The original upload: PDFs open in the browser (a citation adds `#page=N`), other files
    download."""
    item = _get_or_404(session, item_id, user.id)
    path = Path(item.source)
    if item.source_type not in (SourceType.pdf, SourceType.file) or not path.exists():
        raise HTTPException(404, "This item has no stored file")
    suffix = path.suffix.lower()
    filename = f"{item.title[:100]}{suffix}".replace('"', "")
    return FileResponse(
        path,
        media_type=MEDIA_TYPES.get(suffix, "application/octet-stream"),
        filename=filename,
        content_disposition_type="inline" if suffix == ".pdf" else "attachment",
    )


@router.post("/{item_id}/reprocess", response_model=ItemOut, status_code=202)
def reprocess_item(item_id: int, session: SessionDep, user: CurrentUser) -> Item:
    """Queue an item to be processed again, for example after a failure."""
    item = _get_or_404(session, item_id, user.id)
    if item.status in (ItemStatus.queued, ItemStatus.processing):
        raise HTTPException(409, "This item is already being processed")
    jobs.enqueue(session, item)
    session.commit()
    return item


@router.put("/{item_id}/tags", response_model=ItemOut)
def set_item_tags(item_id: int, body: TagsIn, session: SessionDep, user: CurrentUser) -> Item:
    """Replace an item's tags with the user's own. Reprocessing keeps them from then on."""
    item = _get_or_404(session, item_id, user.id)
    names = list(dict.fromkeys(t for t in (clean_tag(raw) for raw in body.tags) if t))
    item.tags = get_or_create_tags(session, names, user.id)
    item.tags_edited = True
    session.flush()
    delete_unused_tags(session, user.id)
    session.commit()
    session.refresh(item, ["tags"])
    return item


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, session: SessionDep, user: CurrentUser) -> Response:
    item = _get_or_404(session, item_id, user.id)
    stored = Path(item.source) if item.source_type in (SourceType.pdf, SourceType.file) else None
    session.delete(item)
    session.flush()
    delete_unused_tags(session, user.id)
    session.commit()
    if stored is not None:
        stored.unlink(missing_ok=True)
    return Response(status_code=204)


def _get_or_404(session, item_id: int, user_id: int) -> Item:
    item = session.get(Item, item_id, options=[selectinload(Item.tags)])
    # Someone else's item answers 404, not 403, so ids reveal nothing.
    if item is None or item.user_id != user_id:
        raise HTTPException(404, "Item not found")
    return item


def _title_from_filename(name: str | None) -> str:
    stem = Path(name or "Untitled").stem.replace("_", " ").strip()
    return stem or "Untitled"


def _store_upload(file: UploadFile) -> tuple[SourceType, str]:
    """Check the type and size of an upload and save it. PDFs are recognised by their first
    bytes, other documents by extension."""
    settings = get_settings()
    head = file.file.read(5)
    if head == b"%PDF-":
        kind, suffix = SourceType.pdf, ".pdf"
    else:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in FILE_EXTENSIONS:
            raise HTTPException(
                415, "Recall can read PDF, Word (.docx), Markdown (.md) and text (.txt) files"
            )
        kind = SourceType.file
    limit = settings.max_upload_mb * 1024 * 1024
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{uuid.uuid4().hex}{suffix}"
    size = len(head)
    with dest.open("wb") as out:
        out.write(head)
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"Files can be up to {settings.max_upload_mb} MB")
            out.write(chunk)
    return kind, str(dest)


def delete_unused_tags(session, user_id: int) -> None:
    used = select(item_tags.c.tag_id)
    session.execute(sa_delete(Tag).where(Tag.user_id == user_id, Tag.id.not_in(used)))
