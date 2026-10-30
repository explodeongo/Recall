"""a printable PDF kept for a saved web page (Wikipedia's), shown as pages in the Read tab

Revision ID: 0021
Revises: 0020
"""

import sqlalchemy as sa

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("pages_file", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("items", "pages_file")
