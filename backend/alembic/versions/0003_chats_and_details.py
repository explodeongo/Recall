"""saved chats, page-long summaries, and hand-edited tags

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("details", postgresql.JSONB))
    op.add_column(
        "items",
        sa.Column("tags_edited", sa.Boolean, nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "chats",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id", ondelete="SET NULL")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_chats_updated_at", "chats", ["updated_at"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "chat_id", sa.Integer, sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("sources", postgresql.JSONB),
        sa.Column("cited", postgresql.JSONB),
        sa.Column("not_found", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("search_query", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_chat_messages_chat_id", "chat_messages", ["chat_id"])


def downgrade() -> None:
    op.drop_table("chat_messages")
    op.drop_table("chats")
    op.drop_column("items", "tags_edited")
    op.drop_column("items", "details")
