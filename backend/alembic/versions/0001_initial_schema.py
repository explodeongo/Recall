"""initial schema: items, chunks, tags, item_tags, jobs

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

source_type = postgresql.ENUM("pdf", "url", name="source_type", create_type=False)
item_status = postgresql.ENUM(
    "queued", "processing", "ready", "failed", name="item_status", create_type=False
)
job_status = postgresql.ENUM(
    "queued", "running", "done", "failed", name="job_status", create_type=False
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for enum in (source_type, item_status, job_status):
        enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("source_type", source_type, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("summary", sa.Text),
        sa.Column("status", item_status, nullable=False, server_default="queued"),
        sa.Column("error", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_items_created_at", "items", ["created_at"])

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
    )

    op.create_table(
        "item_tags",
        sa.Column(
            "item_id", sa.Integer, sa.ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "tag_id", sa.Integer, sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
        ),
    )
    op.create_index("ix_item_tags_tag_id", "item_tags", ["tag_id"])

    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "item_id", sa.Integer, sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("page", sa.Integer),
        sa.Column("embedding", Vector(384)),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR,
            sa.Computed("to_tsvector('english', chunk_text)", persisted=True),
        ),
        sa.UniqueConstraint("item_id", "chunk_index", name="uq_chunks_item_index"),
    )
    op.create_index("ix_chunks_item_id", "chunks", ["item_id"])
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX ix_chunks_tsv ON chunks USING gin (tsv)")

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "item_id", sa.Integer, sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("status", job_status, nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_jobs_item_id", "jobs", ["item_id"])
    op.create_index(
        "ix_jobs_queued", "jobs", ["created_at"], postgresql_where=sa.text("status = 'queued'")
    )


def downgrade() -> None:
    for table in ("jobs", "chunks", "item_tags", "tags", "items"):
        op.drop_table(table)
    for enum in (job_status, item_status, source_type):
        enum.drop(op.get_bind(), checkfirst=True)
