"""what a chat question was limited to: pinned items and tags, and where answers could come from

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("context", postgresql.JSONB))


def downgrade() -> None:
    op.drop_column("chat_messages", "context")
