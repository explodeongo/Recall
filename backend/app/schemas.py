from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models import ItemStatus, SourceType
from app.services.search import SearchMode


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


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    chunk_index: int
    chunk_text: str
    page: int | None


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    mode: SearchMode = SearchMode.hybrid


class SourceOut(BaseModel):
    """One numbered passage given to the model; `n` is the number used in [n] citations."""

    model_config = ConfigDict(from_attributes=True)

    n: int
    chunk_id: int
    item_id: int
    title: str
    source_type: SourceType
    source: str
    page: int | None
    text: str


class AskOut(BaseModel):
    answer: str
    not_found: bool
    sources: list[SourceOut]
    cited: list[int]
    timings: dict[str, float | None]
