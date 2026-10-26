"""an answer saved to the library as a note remembers which note it became

Revision ID: 0018
Revises: 0017
"""

import sqlalchemy as sa

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column("saved_item_id", sa.Integer, sa.ForeignKey("items.id", ondelete="SET NULL")),
    )


def downgrade() -> None:
    op.drop_column("chat_messages", "saved_item_id")
