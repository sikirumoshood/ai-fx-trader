"""Add auto_execute and auto_lot_size to schedules

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedules",
        sa.Column("auto_execute", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "schedules",
        sa.Column("auto_lot_size", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("schedules", "auto_lot_size")
    op.drop_column("schedules", "auto_execute")
