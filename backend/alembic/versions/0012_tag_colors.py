"""tag colors, and tags the user made themselves (kept even when no item uses them)

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tags", sa.Column("color", sa.String(7)))
    op.add_column(
        "tags", sa.Column("user_made", sa.Boolean, nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column("tags", "user_made")
    op.drop_column("tags", "color")
