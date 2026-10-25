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
    details: dict | None
    note: str | None
    tags_edited: bool
    status: ItemStatus
    error: str | None
    created_at: datetime
    tags: list[TagOut]


class TagsIn(BaseModel):
    tags: list[str] = Field(max_length=12)


class UrlIn(BaseModel):
    url: HttpUrl


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    chunk_index: int
    chunk_text: str
    page: int | None
    start_char: int | None
    end_char: int | None


class PageOut(BaseModel):
    page: int | None
    text: str


class ContentOut(BaseModel):
    """The item's full text, split into pages; offsets count across pages joined by a blank
    line."""

    pages: list[PageOut]


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    mode: SearchMode | None = None  # None: the server's configured mode


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
    start_char: int | None = None
    end_char: int | None = None
    kind: str = "text"


class AskOut(BaseModel):
    answer: str
    not_found: bool
    sources: list[SourceOut]
    cited: list[int]
    timings: dict[str, float | None]


class ChatCreate(BaseModel):
    item_id: int | None = None


class ChatRename(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class MessageIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    sources: list[SourceOut] | None
    cited: list[int] | None
    not_found: bool
    search_query: str | None
    created_at: datetime


class ChatSummary(BaseModel):
    id: int
    title: str
    item_id: int | None
    item_title: str | None
    message_count: int
    updated_at: datetime


class ChatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    item_id: int | None
    created_at: datetime
    updated_at: datetime
    messages: list[MessageOut]


class SignupIn(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=200)
    name: str | None = Field(default=None, max_length=200)


class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str | None


class HighlightIn(BaseModel):
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    note: str | None = Field(default=None, max_length=5000)


class HighlightNoteIn(BaseModel):
    note: str | None = Field(default=None, max_length=5000)


class HighlightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    start_char: int
    end_char: int
    quote: str
    note: str | None
    created_at: datetime


class HighlightWithItem(HighlightOut):
    item_title: str


class NoteIn(BaseModel):
    note: str = Field(max_length=50_000)


class SearchItem(BaseModel):
    id: int
    title: str
    source_type: SourceType
    status: ItemStatus


class SearchPassage(BaseModel):
    item_id: int
    title: str
    text: str
    page: int | None
    start_char: int | None
    end_char: int | None
    kind: str


class SearchHighlight(BaseModel):
    id: int
    item_id: int
    item_title: str
    quote: str
    note: str | None
    start_char: int
    end_char: int


class SearchChat(BaseModel):
    id: int
    title: str


class SearchOut(BaseModel):
    items: list[SearchItem]
    passages: list[SearchPassage]
    highlights: list[SearchHighlight]
    chats: list[SearchChat]
    tags: list[str]
