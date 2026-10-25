"""more source types: notes, uploaded documents (Word, Markdown, text) and YouTube videos

Revision ID: 0007
Revises: 0006
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for value in ("note", "file", "youtube"):
        op.execute(f"ALTER TYPE source_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # Postgres can't drop enum values; the unused values are harmless.
    pass
