"""job scheduling: retry backoff and recovery of jobs from crashed workers

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "run_after", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.drop_index("ix_jobs_queued", table_name="jobs")
    op.create_index(
        "ix_jobs_queued", "jobs", ["run_after"], postgresql_where=sa.text("status = 'queued'")
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_queued", table_name="jobs")
    op.create_index(
        "ix_jobs_queued", "jobs", ["created_at"], postgresql_where=sa.text("status = 'queued'")
    )
    op.drop_column("jobs", "run_after")
