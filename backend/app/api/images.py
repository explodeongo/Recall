from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile

from app.deps import CurrentUser, SessionDep
from app.models import Item, ItemImage
from app.schemas import ImageOut
from app.services import images

router = APIRouter(prefix="/images", tags=["images"])


@router.get("/{image_id}")
def get_image(image_id: int, session: SessionDep, user: CurrentUser) -> Response:
    """A picture's bytes. Always a JPEG Recall re-encoded itself, never the original upload."""
    image = session.get(ItemImage, image_id)
    if image is None or image.user_id != user.id:
        raise HTTPException(404, "Image not found")
    data = images.files.read(image.key)
    if data is None:
        raise HTTPException(404, "Image not found")
    return Response(
        data,
        media_type=image.mime,
        headers={
            # An id's picture never changes, so browsers can keep it.
            "Cache-Control": "private, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
        },
    )


@router.post("", response_model=ImageOut, status_code=201)
def upload_image(
    session: SessionDep,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    item_id: Annotated[int | None, Form()] = None,
    alt: Annotated[str | None, Form()] = None,
) -> ItemImage:
    """Add a picture to a note: an item's note (`item_id`), or a note being written (no
    `item_id`; it's attached when the note is saved). Notes refer to it as
    ![what it shows](image:ID)."""
    if item_id is not None:
        item = session.get(Item, item_id)
        if item is None or item.user_id != user.id:
            raise HTTPException(404, "Item not found")
    data = file.file.read(images.MAX_UPLOAD_BYTES + 1)
    if len(data) > images.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Pictures can be up to 10 MB")
    picture = images.normalize(data)
    if picture is None:
        raise HTTPException(422, "That file isn't a picture Recall can read")
    image = images.store(
        session, user.id, picture, item_id=item_id, role="upload", alt=(alt or "").strip() or None
    )
    session.commit()
    return image
