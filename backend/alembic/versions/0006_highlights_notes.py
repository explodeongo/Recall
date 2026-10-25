"""highlights and notes, and chunks that come from them

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("note", sa.Text))
    # "text" chunks come from the document, "note" chunks from the reader's notes and highlights.
    op.add_column("chunks", sa.Column("kind", sa.String(16), nullable=False, server_default="text"))
    op.create_table(
        "highlights",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "item_id", sa.Integer, sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("start_char", sa.Integer, nullable=False),
        sa.Column("end_char", sa.Integer, nullable=False),
        sa.Column("quote", sa.Text, nullable=False),
        sa.Column("note", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_highlights_item_id", "highlights", ["item_id"])
    op.create_index("ix_highlights_user_id", "highlights", ["user_id"])


def downgrade() -> None:
    op.drop_table("highlights")
    op.drop_column("chunks", "kind")
    op.drop_column("items", "note")
