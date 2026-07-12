"""Consolidate inline DDL into Alembic-managed migrations

Adds processed_emails table and users.last_inbound_at column that
previously existed only as inline DDL in db.run_migrations().

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "processed_emails" not in tables:
        op.create_table(
            "processed_emails",
            sa.Column("email_id", sa.String(255), nullable=False),
            sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("email_id"),
        )
    
    # Check if last_inbound_at column exists in users
    columns = [col["name"] for col in inspector.get_columns("users")]
    if "last_inbound_at" not in columns:
        op.add_column(
            "users",
            sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("users", "last_inbound_at")
    op.drop_table("processed_emails")
