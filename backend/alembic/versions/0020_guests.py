"""guest accounts for the public demo, and a daily count of LLM calls

Revision ID: 0020
Revises: 0019
"""

import sqlalchemy as sa

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("is_guest", sa.Boolean, nullable=False, server_default="false")
    )
    op.create_index(
        "ix_users_guests", "users", ["created_at"], postgresql_where=sa.text("is_guest")
    )
    op.create_table(
        "llm_calls",
        sa.Column("day", sa.Date, primary_key=True),
        sa.Column("calls", sa.Integer, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("llm_calls")
    op.drop_index("ix_users_guests", table_name="users")
    op.drop_column("users", "is_guest")
