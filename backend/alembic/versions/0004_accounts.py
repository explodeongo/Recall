"""accounts: users, sessions, and an owner on items, tags and chats

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("name", sa.String(200)),
        sa.Column("password_hash", sa.String(300), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])

    # Existing rows keep a null owner until the first account claims them.
    for table in ("items", "tags", "chats"):
        op.add_column(
            table,
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE")),
        )
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])

    # Tag names were unique across the whole database; now they're unique per person.
    op.drop_constraint("tags_name_key", "tags", type_="unique")
    op.create_unique_constraint(
        "uq_tags_user_name", "tags", ["user_id", "name"], postgresql_nulls_not_distinct=True
    )


def downgrade() -> None:
    op.drop_constraint("uq_tags_user_name", "tags", type_="unique")
    op.create_unique_constraint("tags_name_key", "tags", ["name"])
    for table in ("chats", "tags", "items"):
        op.drop_index(f"ix_{table}_user_id", table_name=table)
        op.drop_column(table, "user_id")
    op.drop_table("user_sessions")
    op.drop_table("users")
