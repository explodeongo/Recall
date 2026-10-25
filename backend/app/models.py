import enum
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
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


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, name="source_type"))
    source: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
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

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)

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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
