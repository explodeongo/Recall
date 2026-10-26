"""question types for flashcards: multiple choice and true/false, with an explanation

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cards", sa.Column("kind", sa.String(16), nullable=False, server_default="flashcard")
    )
    op.add_column("cards", sa.Column("options", postgresql.JSONB))
    op.add_column("cards", sa.Column("explanation", sa.Text))


def downgrade() -> None:
    op.drop_column("cards", "explanation")
    op.drop_column("cards", "options")
    op.drop_column("cards", "kind")
