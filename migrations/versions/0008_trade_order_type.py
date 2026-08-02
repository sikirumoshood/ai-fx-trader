"""Add order_type to trades

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("order_type", sa.String(16), nullable=False, server_default="MARKET"))


def downgrade() -> None:
    op.drop_column("trades", "order_type")
