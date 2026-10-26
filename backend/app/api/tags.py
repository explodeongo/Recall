from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from app.deps import CurrentUser, SessionDep
from app.models import Tag
from app.schemas import TagCreate, TagPatch, TagWithCount
from app.services import tags as tag_service
from app.services.enrich import clean_tag

router = APIRouter(prefix="/tags", tags=["tags"])


def _out(tag: Tag, count: int) -> TagWithCount:
    return TagWithCount(
        id=tag.id,
        name=tag.name,
        color=tag_service.color_of(tag),
        item_count=count,
        user_made=tag.user_made,
    )


@router.get("", response_model=list[TagWithCount])
def list_tags(session: SessionDep, user: CurrentUser) -> list[TagWithCount]:
    """Every tag with its color and how many items use it, most used first."""
    return [_out(tag, n) for tag, n in tag_service.usage(session, user.id)]


@router.post("", response_model=TagWithCount, status_code=201)
def create_tag(body: TagCreate, session: SessionDep, user: CurrentUser) -> TagWithCount:
    """Make a tag before using it. If it already exists, it's kept and given this color."""
    name = clean_tag(body.name)
    if not name:
        raise HTTPException(422, "Tags can use letters, numbers, spaces and - . + #")
    tag = session.scalars(select(Tag).where(Tag.user_id == user.id, Tag.name == name)).first()
    if tag is None:
        tag = Tag(user_id=user.id, name=name)
        session.add(tag)
    tag.user_made = True
    if body.color:
        tag.color = body.color.lower()
    session.commit()
    count = dict((t.id, n) for t, n in tag_service.usage(session, user.id)).get(tag.id, 0)
    return _out(tag, count)


@router.patch("/{tag_id}", response_model=TagWithCount)
def update_tag(tag_id: int, body: TagPatch, session: SessionDep, user: CurrentUser) -> TagWithCount:
    """Rename or recolor a tag. Renaming it to an existing tag's name merges the two."""
    tag = _get(session, tag_id, user.id)
    if body.color is not None:
        tag.color = body.color.lower()
    if body.name is not None:
        name = clean_tag(body.name)
        if not name:
            raise HTTPException(422, "Tags can use letters, numbers, spaces and - . + #")
        if name != tag.name:
            other = session.scalars(
                select(Tag).where(Tag.user_id == user.id, Tag.name == name)
            ).first()
            if other is not None:
                other.color = other.color or tag.color
                tag_service.merge(session, tag, other)
                tag = other
            else:
                tag.name = name
    tag.user_made = True
    session.commit()
    count = dict((t.id, n) for t, n in tag_service.usage(session, user.id)).get(tag.id, 0)
    return _out(tag, count)


@router.delete("/{tag_id}", status_code=204)
def delete_tag(tag_id: int, session: SessionDep, user: CurrentUser) -> Response:
    """Remove a tag from every item and delete it. The items stay."""
    session.delete(_get(session, tag_id, user.id))
    session.commit()
    return Response(status_code=204)


def _get(session, tag_id: int, user_id: int) -> Tag:
    tag = session.get(Tag, tag_id)
    if tag is None or tag.user_id != user_id:
        raise HTTPException(404, "Tag not found")
    return tag
