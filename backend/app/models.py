import enum
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    Computed,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import get_settings
from app.db import Base

EMBEDDING_DIM = get_settings().embedding_dim


class SourceType(enum.StrEnum):
    pdf = "pdf"
    url = "url"
    note = "note"  # text typed or pasted into Recall; `source` holds the text
    file = "file"  # an uploaded Word, Markdown or text file; `source` is its stored path
    youtube = "youtube"  # a video, read from its captions; `source` is the video URL


class ItemStatus(enum.StrEnum):
    queued = "queued"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class JobStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


item_tags = Table(
    "item_tags",
    Base.metadata,
    Column("item_id", ForeignKey("items.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str | None] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(300))
    # A visitor trying the public demo on a copy of the demo library (services/guest.py).
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserSession(Base):
    """A signed-in browser. The cookie holds a random token; only its SHA-256 is stored."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()


class ApiToken(Base):
    """A personal access token for the API and the MCP server ("Authorization: Bearer ...").
    Shown once when made; only its SHA-256 is stored, plus a prefix to tell tokens apart."""

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()


class ItemImage(Base):
    """A picture: an item's cover, a figure from its document, or one added to a note.

    `position` is where it sits in the item's full text (offsets as in Chunk.start_char), so
    the reader can show it in place and answers can show the figures beside a cited passage.
    The bytes live in the file store (services/files.py), downscaled and re-encoded on save.
    """

    __tablename__ = "item_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # None for an image added to a note that isn't saved yet.
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(12))  # "cover", "figure" or "upload"
    key: Mapped[str] = mapped_column(Text)
    mime: Mapped[str] = mapped_column(String(32))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    alt: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[int | None] = mapped_column(Integer)
    source_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Owner. Null only for rows made outside the app (the evaluation) or saved before accounts
    # existed; the first account to sign up claims those.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(500))
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, name="source_type"))
    source: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    # The page-long summary: {"overview": str, "key_points": [str], "sections": [{heading, body}]}
    details: Mapped[dict | None] = mapped_column(JSONB)
    # The cleaned full text for the reader: [{"page": int | None, "text": str}], paragraphs
    # separated by blank lines. Joined with blank lines, it's the text chunk offsets refer to.
    content: Mapped[list | None] = mapped_column(JSONB)
    # What the item is about (title, summary, tags) as one vector, so search can find a
    # document by its topic even when its text never uses the searched words.
    summary_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    starred: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Archived items leave the main list but stay searchable and answerable.
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The reader's own free-form note on the item.
    note: Mapped[str | None] = mapped_column(Text)
    # Set when the user edits the tags by hand, so reprocessing keeps their choice.
    tags_edited: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # A title the person typed when saving, or renamed to: kept when the item is read again.
    title_edited: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # The picture shown for it in lists (an ItemImage; no foreign key, it's replaced freely).
    cover_image_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[ItemStatus] = mapped_column(
        Enum(ItemStatus, name="item_status"), default=ItemStatus.queued
    )
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="Chunk.chunk_index"
    )
    tags: Mapped[list["Tag"]] = relationship(secondary=item_tags, back_populates="items")
    highlights: Mapped[list["Highlight"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="Highlight.start_char"
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_text: Mapped[str] = mapped_column(Text)
    # "text": from the document. "note": from the reader's notes and highlights, so questions
    # can be answered from them too (their chunk_index is negative to stay out of the way).
    kind: Mapped[str] = mapped_column(String(16), default="text", server_default="text")
    # PDF page the chunk starts on, so citations can jump to it. Null for web articles.
    page: Mapped[int | None] = mapped_column(Integer)
    # Where the chunk sits in the item's joined content, so the reader can highlight it.
    start_char: Mapped[int | None] = mapped_column(Integer)
    end_char: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    # Filled by the database from chunk_text; used for the keyword half of hybrid search.
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', chunk_text)", persisted=True)
    )

    item: Mapped[Item] = relationship(back_populates="chunks")


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "name", name="uq_tags_user_name", postgresql_nulls_not_distinct=True
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(64))
    # "#rrggbb". Null means "pick one from the name" (services/tags.py), so every tag has one.
    color: Mapped[str | None] = mapped_column(String(7))
    # Made in the tag manager: kept even when no item uses it. Tags the model or the item
    # editor create disappear when their last item goes.
    user_made: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    items: Mapped[list[Item]] = relationship(secondary=item_tags, back_populates="tags")


class Job(Base):
    """A unit of background work. Workers claim rows with FOR UPDATE SKIP LOCKED."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"), default=JobStatus.queued, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    # Retries wait until this time; see services/jobs.py.
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Chat(Base):
    """A saved conversation. With `item_id` set, it only searches that one document."""

    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    item: Mapped[Item | None] = relationship()
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="chat", cascade="all, delete-orphan", order_by="ChatMessage.id"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # "user" or "assistant"
    content: Mapped[str] = mapped_column(Text)
    # Assistant messages keep what they were built from, so a reopened chat shows its citations.
    sources: Mapped[list | None] = mapped_column(JSONB)
    cited: Mapped[list | None] = mapped_column(JSONB)
    not_found: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # A follow-up rewritten to stand on its own ("what about its height?" -> "B-tree height").
    search_query: Mapped[str | None] = mapped_column(Text)
    # On questions: what the answer was limited to, as asked ("@" items and tags, and the
    # source: library, both or web). {"items": [{"id", "title"}], "tags": [...], "source": ...}
    context: Mapped[dict | None] = mapped_column(JSONB)
    # On answers saved to the library: the note they became.
    saved_item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id", ondelete="SET NULL"))
    # On answers: follow-up questions to offer next.
    suggestions: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chat: Mapped[Chat] = relationship(back_populates="messages")


class Highlight(Base):
    """A passage the reader marked in an item's full text, optionally with a note."""

    __tablename__ = "highlights"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    start_char: Mapped[int] = mapped_column(Integer)
    end_char: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    item: Mapped[Item] = relationship(back_populates="highlights")


class Card(Base):
    """A flashcard made from an item, scheduled with spaced repetition (services/review.py)."""

    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    # "flashcard" (recall the answer), "multiple_choice" or "true_false" (pick from `options`;
    # `answer` is the right option, word for word).
    kind: Mapped[str] = mapped_column(String(16), default="flashcard", server_default="flashcard")
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str] | None] = mapped_column(JSONB)
    # Why the answer is right, shown after answering.
    explanation: Mapped[str | None] = mapped_column(Text)
    # The passage the card was made from, in the item's full text.
    start_char: Mapped[int | None] = mapped_column(Integer)
    end_char: Mapped[int | None] = mapped_column(Integer)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    interval_days: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    ease: Mapped[float] = mapped_column(Float, default=2.5, server_default="2.5")
    reps: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    lapses: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    item: Mapped[Item] = relationship()


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    grade: Mapped[str] = mapped_column(String(8))
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
