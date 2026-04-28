"""add sessions column to schedules

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-28

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "schedules",
        sa.Column("sessions", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("schedules", "sessions")
