"""Add journal entries table

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("pair", sa.String(12), nullable=False),
        sa.Column("lot_size", sa.Float(), nullable=False),
        sa.Column("strategy", sa.String(32), nullable=False),
        sa.Column("session", sa.String(16), nullable=False),
        sa.Column("trade_mode", sa.String(16), nullable=False, server_default="MANUAL"),
        sa.Column("amount_usd", sa.Float(), nullable=False),
        sa.Column(
            "outcome",
            sa.Enum("WIN", "LOSS", name="journaloutcome"),
            nullable=False,
        ),
        sa.Column("trade_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("journal_entries")
    op.execute("DROP TYPE IF EXISTS journaloutcome")
