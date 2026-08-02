"""Add indicator to schedules

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedules",
        sa.Column("indicator", sa.String(16), nullable=False, server_default="kronos"),
    )


def downgrade() -> None:
    op.drop_column("schedules", "indicator")
