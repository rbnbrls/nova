"""Create task_notes table and add is_template column to tasks (Phase 45)

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("tasks")]
    tables = inspector.get_table_names()

    # 1. Add is_template column to tasks
    if "is_template" not in columns:
        op.add_column(
            "tasks",
            sa.Column("is_template", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )

    # 2. Create task_notes table
    if "task_notes" not in tables:
        op.create_table(
            "task_notes",
            sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
            sa.Column("task_id", sa.UUID(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("author_id", sa.UUID(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_task_notes_task_id", "task_notes", ["task_id"])
        op.create_index("ix_task_notes_created_at", "task_notes", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_task_notes_created_at", table_name="task_notes")
    op.drop_index("ix_task_notes_task_id", table_name="task_notes")
    op.drop_table("task_notes")
    op.drop_column("tasks", "is_template")
