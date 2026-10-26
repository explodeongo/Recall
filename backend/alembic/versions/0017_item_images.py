"""pictures: item covers, figures from documents, and images added to notes

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "item_images",
        sa.Column("id", sa.Integer, primary_key=True),
        # Follows the item's owner; items saved before accounts existed have none.
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id", ondelete="CASCADE")),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("mime", sa.String(32), nullable=False),
        sa.Column("width", sa.Integer, nullable=False),
        sa.Column("height", sa.Integer, nullable=False),
        sa.Column("alt", sa.Text),
        sa.Column("page", sa.Integer),
        sa.Column("position", sa.Integer),
        sa.Column("source_url", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_item_images_item_id", "item_images", ["item_id"])
    op.add_column("items", sa.Column("cover_image_id", sa.Integer))


def downgrade() -> None:
    op.drop_column("items", "cover_image_id")
    op.drop_table("item_images")
