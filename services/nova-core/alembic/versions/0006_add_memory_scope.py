"""Add scope column to memories table (private/household)

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "memories",
        sa.Column("scope", sa.Text(), server_default=sa.text("'private'"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("memories", "scope")
