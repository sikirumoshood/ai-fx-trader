"""Add notify_email to schedules

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedules",
        sa.Column("notify_email", sa.String(254), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("schedules", "notify_email")
