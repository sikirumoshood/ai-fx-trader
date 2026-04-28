"""add schedule execution history table

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "schedule_executions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("schedule_id", sa.String(), sa.ForeignKey("schedules.id"), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("signal_id", sa.String(), sa.ForeignKey("signals.id"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_schedule_executions_schedule_id_started_at",
        "schedule_executions",
        ["schedule_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_schedule_executions_schedule_id_started_at", table_name="schedule_executions")
    op.drop_table("schedule_executions")
