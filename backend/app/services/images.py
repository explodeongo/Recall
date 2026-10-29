"""Pictures for items: a cover for lists, figures from the document for the reader and for
answers, and images people add to their notes.

Every image is decoded and re-encoded through MuPDF before it's kept (as JPEG, at most
MAX_SIDE pixels on the long side), so what's served back is always a plain raster image,
never the original bytes (an SVG with script in it, say). Each one remembers where it sits
in the item's full text (`position`), found from the paragraph it followed in the source.
"""

import hashlib
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Item, ItemImage
from app.services import files

log = logging.getLogger("recall.images")

MAX_SIDE = 1600
COVER_SIDE = 960
MIN_SIDE = 120  # smaller is an icon, a button or a tracking pixel
MAX_FIGURES = 10
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
# How a note refers to a picture added to it: ![what it shows](image:12)
IMAGE_TOKEN = re.compile(r"!\[([^\]\n]{0,300})\]\(image:(\d+)\)")


@dataclass(frozen=True)
class ExtractedImage:
    """A picture found while reading a source. One of `data` (bytes), `url` (to download) or
    `image_id` (an image already uploaded to a note) is set."""

    role: str  # "cover", "figure" or "upload"
    data: bytes | None = None
    url: str | None = None
    image_id: int | None = None
    alt: str | None = None
    page: int | None = None
    anchor: str | None = None  # text of the paragraph it came after


@dataclass(frozen=True)
class Picture:
    data: bytes
    mime: str
    width: int
    height: int


def normalize(data: bytes, max_side: int = MAX_SIDE) -> Picture | None:
    """Decode any image MuPDF reads (JPEG, PNG, GIF, WebP, BMP, TIFF, SVG…), scale it down to
    `max_side`, and re-encode it as JPEG. None if it isn't a single image."""
    import pymupdf  # here, not at the top: it adds about 130 MB to every process that loads it

    try:
        doc = pymupdf.open(stream=data)
    except Exception:
        return None
    with doc:
        if doc.is_pdf or doc.page_count != 1:
            return None
        page = doc[0]
        width, height = page.rect.width, page.rect.height
        if width < 1 or height < 1:
            return None
        scale = min(1.0, max_side / max(width, height))
        try:
            pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        except Exception:
            return None
        return Picture(pix.tobytes("jpg", jpg_quality=82), "image/jpeg", pix.width, pix.height)


def render_pdf_page(data: bytes, page_number: int = 0, width: int = COVER_SIDE) -> bytes | None:
    """A page of a PDF as a PNG, `width` pixels wide: a PDF's cover."""
    import pymupdf

    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            page = doc[page_number]
            scale = width / max(page.rect.width, 1)
            return page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes("png")
    except Exception:
        return None


def store(session: Session, user_id: int, picture: Picture, **fields) -> ItemImage:
    image = ItemImage(
        user_id=user_id,
        key=files.save(picture.data, ".jpg"),
        mime=picture.mime,
        width=picture.width,
        height=picture.height,
        **fields,
    )
    session.add(image)
    session.flush()
    return image


def remove(session: Session, images: list[ItemImage]) -> None:
    for image in images:
        files.delete(image.key)
        session.delete(image)


def url_of(image_id: int) -> str:
    return f"/images/{image_id}"


Fetch = Callable[[str], bytes | None]


def attach(
    session: Session,
    item: Item,
    found: list[ExtractedImage],
    full_text: str,
    page_starts: dict[int, int],
    fetch: Fetch,
) -> None:
    """Replace the item's cover and figures with those `found`, place each in the text, and
    adopt images added to its note. Pictures that can't be fetched or decoded are skipped."""
    old = session.scalars(
        select(ItemImage).where(ItemImage.item_id == item.id, ItemImage.role != "upload")
    ).all()
    remove(session, list(old))
    item.cover_image_id = None

    seen: set[str] = set()
    cover: ItemImage | None = None
    first_picture: ItemImage | None = None
    figures = 0
    for img in found:
        position = _place(img, full_text, page_starts)
        if img.image_id is not None:
            upload = session.get(ItemImage, img.image_id)
            if upload is None or upload.user_id != item.user_id or upload.role != "upload":
                continue
            upload.item_id, upload.position = item.id, position
            upload.alt = upload.alt or img.alt
            first_picture = first_picture or upload
            continue
        if img.role == "figure" and figures >= MAX_FIGURES:
            continue
        same_as = _picture_key(img.url)
        if same_as and same_as in seen:
            continue  # the same picture at another size (a page's cover is often a figure)
        data = img.data if img.data is not None else (fetch(img.url) if img.url else None)
        if not data:
            continue
        digest = hashlib.sha1(data).hexdigest()
        if digest in seen:
            continue
        seen.update(k for k in (digest, same_as) if k)
        picture = normalize(data, COVER_SIDE if img.role == "cover" else MAX_SIDE)
        if picture is None:
            continue
        if img.role == "figure" and (
            min(picture.width, picture.height) < MIN_SIDE
            or max(picture.width, picture.height) > 6 * min(picture.width, picture.height)
        ):
            continue  # icons, spacers and decorative strips
        stored = store(
            session,
            item.user_id,
            picture,
            item_id=item.id,
            role=img.role,
            alt=(img.alt or "").strip()[:300] or None,
            page=img.page,
            position=None if img.role == "cover" else position,
            source_url=img.url,
        )
        if img.role == "cover":
            cover = cover or stored
        else:
            figures += 1
            first_picture = first_picture or stored
    chosen = cover or first_picture
    item.cover_image_id = chosen.id if chosen else None


def _picture_key(url: str | None) -> str | None:
    """A URL without its size and query: thumbnails of one picture share it."""
    if not url:
        return None
    return re.sub(r"/\d{2,4}px-", "/", url.split("?")[0])


def _place(img: ExtractedImage, full_text: str, page_starts: dict[int, int]) -> int | None:
    """Where the picture goes in the text: just after the paragraph it followed, or at the top
    of its page when that paragraph can't be found."""
    from app.services.review import locate_quote

    if img.anchor:
        anchor = " ".join(img.anchor.split())[:120]
        # On its own page first: a heading like "Multi-Head Attention" can appear earlier too.
        lo, hi = 0, len(full_text)
        if img.page is not None and img.page in page_starts:
            lo = page_starts[img.page]
            hi = min((v for k, v in page_starts.items() if k > img.page), default=len(full_text))
        start = locate_quote(full_text[lo:hi], anchor)
        start = lo + start if start is not None else locate_quote(full_text, anchor)
        if start is not None:
            end = full_text.find("\n\n", start)
            return len(full_text) if end == -1 else end
    if img.page is not None:
        return page_starts.get(img.page)
    return None


def images_near(session: Session, sources: list[dict]) -> None:
    """Give each library source the figures beside its passage (up to two), in place, so an
    answer can show them: those placed in or just after the passage, or on its PDF page."""
    item_ids = {s["item_id"] for s in sources if s.get("item_id")}
    if not item_ids:
        return
    rows = session.scalars(
        select(ItemImage)
        .where(ItemImage.item_id.in_(item_ids), ItemImage.role != "cover")
        .order_by(ItemImage.position)
    ).all()
    by_item: dict[int, list[ItemImage]] = {}
    for row in rows:
        by_item.setdefault(row.item_id, []).append(row)
    for source in sources:
        near = []
        start, end = source.get("start_char"), source.get("end_char")
        for image in by_item.get(source.get("item_id"), []):
            if image.position is not None and start is not None and end is not None:
                hit = start - 200 <= image.position <= end + 400
            else:
                hit = image.page is not None and image.page == source.get("page")
            if hit:
                near.append(
                    {"id": image.id, "alt": image.alt, "width": image.width, "height": image.height}
                )
        source["images"] = near[:2]


def strip_tokens(text: str) -> str:
    """A note's text without its image references, keeping what each picture shows."""
    return IMAGE_TOKEN.sub(lambda m: m.group(1).strip(), text)


def note_images(text: str) -> tuple[str, list[ExtractedImage]]:
    """A typed note's text without image references, and the images it refers to, each
    anchored to the paragraph before it."""
    found = []
    for match in IMAGE_TOKEN.finditer(text):
        before = text[: match.start()].rstrip()
        anchor = before.split("\n\n")[-1].strip() if before else None
        found.append(
            ExtractedImage(
                role="upload", image_id=int(match.group(2)), alt=match.group(1), anchor=anchor
            )
        )
    return IMAGE_TOKEN.sub("", text), found


def delete_for_item(session: Session, item_id: int) -> list[str]:
    """Forget an item's pictures; returns their file keys, to delete once committed."""
    keys = list(session.scalars(select(ItemImage.key).where(ItemImage.item_id == item_id)))
    session.execute(delete(ItemImage).where(ItemImage.item_id == item_id))
    return keys
