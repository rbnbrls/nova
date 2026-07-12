"""Create grocery_items table for household grocery list

Adds a new table `grocery_items` distinct from `tasks` so the grocery list
is a first-class concept. Items remain in the table after purchase for history.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "grocery_items",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Text(), nullable=True),
        sa.Column("added_by", sa.UUID(), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("purchased", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purchased_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["added_by"], ["users.id"], ),
        sa.ForeignKeyConstraint(["purchased_by"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_grocery_items_title", "grocery_items", ["title"])


def downgrade() -> None:
    op.drop_index("ix_grocery_items_title", table_name="grocery_items")
    op.drop_table("grocery_items")
