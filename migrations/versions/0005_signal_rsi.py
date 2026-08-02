"""Add rsi and rsi_advisory columns to signals table

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("signals", sa.Column("rsi", sa.Float(), nullable=True))
    op.add_column("signals", sa.Column("rsi_advisory", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("signals", "rsi_advisory")
    op.drop_column("signals", "rsi")
