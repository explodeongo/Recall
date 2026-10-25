from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Tag, item_tags
from app.schemas import TagWithCount

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=list[TagWithCount])
def list_tags(session: Annotated[Session, Depends(get_session)]) -> list[TagWithCount]:
    rows = session.execute(
        select(Tag.id, Tag.name, func.count(item_tags.c.item_id).label("item_count"))
        .outerjoin(item_tags, item_tags.c.tag_id == Tag.id)
        .group_by(Tag.id)
        .order_by(func.count(item_tags.c.item_id).desc(), Tag.name)
    ).all()
    return [TagWithCount(id=r.id, name=r.name, item_count=r.item_count) for r in rows]
