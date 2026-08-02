"""Add ifvg_threshold to schedules and backtest_runs

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedules",
        sa.Column("ifvg_threshold", sa.Float(), nullable=True, server_default="0.0"),
    )
    op.add_column(
        "backtest_runs",
        sa.Column("ifvg_threshold", sa.Float(), nullable=True, server_default="0.0"),
    )


def downgrade() -> None:
    op.drop_column("schedules", "ifvg_threshold")
    op.drop_column("backtest_runs", "ifvg_threshold")
