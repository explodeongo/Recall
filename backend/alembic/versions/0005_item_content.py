"""full text on items and each chunk's position in it, for the built-in reader

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("content", postgresql.JSONB))
    op.add_column("chunks", sa.Column("start_char", sa.Integer))
    op.add_column("chunks", sa.Column("end_char", sa.Integer))


def downgrade() -> None:
    op.drop_column("chunks", "end_char")
    op.drop_column("chunks", "start_char")
    op.drop_column("items", "content")
