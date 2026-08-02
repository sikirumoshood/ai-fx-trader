"""Add pattern_name and pattern_bias to signals

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("signals", sa.Column("pattern_name", sa.String(64),  nullable=True))
    op.add_column("signals", sa.Column("pattern_bias", sa.String(16),  nullable=True))


def downgrade() -> None:
    op.drop_column("signals", "pattern_bias")
    op.drop_column("signals", "pattern_name")
