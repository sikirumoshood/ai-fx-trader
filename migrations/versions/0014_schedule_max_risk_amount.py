"""Add max_risk_amount to schedules

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedules",
        sa.Column("max_risk_amount", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("schedules", "max_risk_amount")
