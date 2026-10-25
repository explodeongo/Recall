"""starred and archived items, and when each was last opened (for resurfacing)

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "items", sa.Column("starred", sa.Boolean, nullable=False, server_default=sa.false())
    )
    op.add_column(
        "items", sa.Column("archived", sa.Boolean, nullable=False, server_default=sa.false())
    )
    op.add_column("items", sa.Column("last_opened_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    for column in ("last_opened_at", "archived", "starred"):
        op.drop_column("items", column)
