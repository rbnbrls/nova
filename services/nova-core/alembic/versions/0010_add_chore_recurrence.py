"""Add recurrence columns to tasks table and create chore_rotation_log table

Extends the tasks table with columns for recurring chores (recurrence_pattern,
rotation_group, last_rotation_assignee_id, is_chore) and creates a new
chore_rotation_log table for tracking completion history to compute fair-share
metrics and determine next assignee in rotation.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add columns to tasks table
    op.add_column("tasks", sa.Column("recurrence_pattern", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("rotation_group", sa.Text(), nullable=True))
    op.add_column(
        "tasks",
        sa.Column("last_rotation_assignee_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("is_chore", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_foreign_key(
        "fk_tasks_last_rotation_assignee",
        "tasks",
        "users",
        ["last_rotation_assignee_id"],
        ["id"],
    )

    # Create chore_rotation_log table
    op.create_table(
        "chore_rotation_log",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("chore_id", sa.UUID(), nullable=False),
        sa.Column("completed_by", sa.UUID(), nullable=False),
        sa.Column("rotation_group", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chore_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["completed_by"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("chore_rotation_log")
    op.drop_constraint("fk_tasks_last_rotation_assignee", "tasks", type_="foreignkey")
    op.drop_column("tasks", "is_chore")
    op.drop_column("tasks", "last_rotation_assignee_id")
    op.drop_column("tasks", "rotation_group")
    op.drop_column("tasks", "recurrence_pattern")
