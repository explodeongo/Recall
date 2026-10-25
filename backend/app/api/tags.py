from fastapi import APIRouter
from sqlalchemy import func, select

from app.deps import CurrentUser, SessionDep
from app.models import Tag, item_tags
from app.schemas import TagWithCount

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=list[TagWithCount])
def list_tags(session: SessionDep, user: CurrentUser) -> list[TagWithCount]:
    rows = session.execute(
        select(Tag.id, Tag.name, func.count(item_tags.c.item_id).label("item_count"))
        .join(item_tags, item_tags.c.tag_id == Tag.id)
        .where(Tag.user_id == user.id)
        .group_by(Tag.id)
        .order_by(func.count(item_tags.c.item_id).desc(), Tag.name)
    ).all()
    return [TagWithCount(id=r.id, name=r.name, item_count=r.item_count) for r in rows]
