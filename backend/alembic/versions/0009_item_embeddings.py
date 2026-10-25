"""an embedding of each item's title, summary and tags, for "related" search results

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("summary_embedding", Vector(384)))


def downgrade() -> None:
    op.drop_column("items", "summary_embedding")
