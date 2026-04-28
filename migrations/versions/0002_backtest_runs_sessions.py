"""add sessions column to backtest_runs

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-27

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "backtest_runs",
        sa.Column("sessions", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("backtest_runs", "sessions")
