"""Create planned_blocks table for deterministic scheduling (Phase 43)

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "planned_blocks",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("planned_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_occupied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source_event_uid", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("start_time < end_time", name="ck_planned_blocks_time_order"),
    )
    op.create_index("ix_planned_blocks_user_date", "planned_blocks", ["user_id", "planned_date"])
    op.create_index("ix_planned_blocks_task_id", "planned_blocks", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_planned_blocks_task_id", table_name="planned_blocks")
    op.drop_index("ix_planned_blocks_user_date", table_name="planned_blocks")
    op.drop_table("planned_blocks")
