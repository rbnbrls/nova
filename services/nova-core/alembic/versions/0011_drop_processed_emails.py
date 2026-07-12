"""Drop processed_emails table (replaced by IMAP flags — Phase 38)

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("processed_emails")


def downgrade() -> None:
    op.create_table(
        "processed_emails",
        sa.Column("email_id", sa.String(255), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("email_id"),
    )
