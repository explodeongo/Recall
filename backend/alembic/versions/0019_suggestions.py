"""follow-up questions offered under an answer

Revision ID: 0019
Revises: 0018
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("suggestions", postgresql.JSONB))


def downgrade() -> None:
    op.drop_column("chat_messages", "suggestions")
