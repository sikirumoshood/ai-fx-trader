"""Add signal_id and stack_index to trades for stacking support

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("signal_id",   sa.String(),  nullable=True))
    op.add_column("trades", sa.Column("stack_index", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_trades_signal_id", "trades", "signals", ["signal_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_trades_signal_id", "trades", type_="foreignkey")
    op.drop_column("trades", "stack_index")
    op.drop_column("trades", "signal_id")
