from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl

from app.models import ItemStatus, SourceType


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class TagWithCount(TagOut):
    item_count: int


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source_type: SourceType
    source: str
    summary: str | None
    status: ItemStatus
    error: str | None
    created_at: datetime
    tags: list[TagOut]


class UrlIn(BaseModel):
    url: HttpUrl


class AskIn(BaseModel):
    question: str
