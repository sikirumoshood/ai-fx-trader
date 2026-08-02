"""Add indicator to backtest_runs

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "backtest_runs",
        sa.Column("indicator", sa.String(16), nullable=False, server_default="kronos"),
    )


def downgrade() -> None:
    op.drop_column("backtest_runs", "indicator")
