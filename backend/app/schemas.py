from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.models import ItemStatus, SourceType
from app.services.review import Grade
from app.services.search import SearchMode


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str  # "#rrggbb"

    @model_validator(mode="before")
    @classmethod
    def _color(cls, value):
        # ORM tags may have no color stored; give them their default one.
        from app.models import Tag
        from app.services.tags import color_of

        if isinstance(value, Tag):
            return {"id": value.id, "name": value.name, "color": color_of(value)}
        return value


class TagWithCount(TagOut):
    item_count: int
    user_made: bool = False


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class TagPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class MatchOut(BaseModel):
    """Where a search matched inside a document. In `snippet`, matched words are wrapped in
    U+2063 [[ ... ]] U+2063 (see services/library_search.py)."""

    model_config = ConfigDict(from_attributes=True)

    kind: str
    snippet: str
    page: int | None
    chunk_id: int | None
    start_char: int | None
    end_char: int | None


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
    starred: bool
    archived: bool
    last_opened_at: datetime | None
    status: ItemStatus
    error: str | None
    created_at: datetime
    tags: list[TagOut]
    # Only on search results: where in the document the search matched.
    match: MatchOut | None = None


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
    # Off by default here: /ask is the proposal's library-only endpoint (NFR-1), and the
    # evaluation measures it.
    web: bool = False


class SourceOut(BaseModel):
    """One numbered passage given to the model; `n` is the number used in [n] citations."""

    model_config = ConfigDict(from_attributes=True)

    n: int
    chunk_id: int | None  # web passages have no chunk or item; `source` is the page's URL
    item_id: int | None
    title: str
    source_type: SourceType
    source: str
    page: int | None
    text: str
    start_char: int | None = None
    end_char: int | None = None
    kind: str = "text"  # "text", "note" (your notes) or "web"


class AskOut(BaseModel):
    answer: str
    not_found: bool
    web_used: bool = False
    sources: list[SourceOut]
    cited: list[int]
    timings: dict[str, float | None]


class ChatCreate(BaseModel):
    item_id: int | None = None


class ChatRename(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class MessageIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    # Search the web for what the library doesn't cover (answers stay cited, from pages).
    web: bool = True


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
    invite_code: str | None = Field(default=None, max_length=200)


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


class CardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    question: str
    answer: str
    start_char: int | None
    end_char: int | None
    due_at: datetime
    interval_days: float
    reps: int
    lapses: int


class DueCard(CardOut):
    item_title: str
    # How long until the card comes back for each grade: {"again": "10m", "good": "1d", ...}
    next: dict[str, str]


class CardEdit(BaseModel):
    question: str | None = Field(default=None, min_length=1, max_length=2000)
    answer: str | None = Field(default=None, min_length=1, max_length=4000)


class GradeIn(BaseModel):
    grade: Grade


class ReviewStats(BaseModel):
    due: int
    total: int
    reviewed_today: int
    streak_days: int
    next_due_at: datetime | None


class ItemPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    starred: bool | None = None
    archived: bool | None = None


class ConnectionPassage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: int
    text: str
    page: int | None
    start_char: int | None
    end_char: int | None


class ConnectionOut(BaseModel):
    item: ItemOut
    similarity: float
    shared_tags: list[str]
    passage: ConnectionPassage | None


class GraphNode(BaseModel):
    id: int
    title: str
    source_type: SourceType
    tags: list[TagOut]
    created_at: datetime


class GraphEdge(BaseModel):
    source: int
    target: int
    similarity: float


class GraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class ResurfaceOut(BaseModel):
    items: list[ItemOut]
    cards_due: int


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class PasswordConfirm(BaseModel):
    password: str = Field(max_length=200)
