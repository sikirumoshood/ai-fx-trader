"""Add auto_close_profit fields to schedules

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("schedules", sa.Column("auto_close_profit", sa.Boolean(), nullable=True, server_default="false"))
    op.add_column("schedules", sa.Column("auto_close_profit_amount", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("schedules", "auto_close_profit_amount")
    op.drop_column("schedules", "auto_close_profit")
