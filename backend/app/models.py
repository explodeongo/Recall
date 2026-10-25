import enum
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    Computed,
    DateTime,
    Enum,
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
    # Set when the user edits the tags by hand, so reprocessing keeps their choice.
    tags_edited: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    status: Mapped[ItemStatus] = mapped_column(
        Enum(ItemStatus, name="item_status"), default=ItemStatus.queued
    )
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="Chunk.chunk_index"
    )
    tags: Mapped[list["Tag"]] = relationship(secondary=item_tags, back_populates="items")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_text: Mapped[str] = mapped_column(Text)
    # PDF page the chunk starts on, so citations can jump to it. Null for web articles.
    page: Mapped[int | None] = mapped_column(Integer)
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chat: Mapped[Chat] = relationship(back_populates="messages")
