"""Create agent_turns and agent_iterations tables (Phase 1 — response time monitoring)

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_turns",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("total_latency_ms", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("iteration_count", sa.Integer(), nullable=False),
        sa.Column("got_stuck", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_turns_created_at", "agent_turns", ["created_at"])
    op.create_index("ix_agent_turns_user_channel", "agent_turns", ["user", "channel"])

    op.create_table(
        "agent_iterations",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("turn_id", sa.UUID(), nullable=False),
        sa.Column("iteration_num", sa.Integer(), nullable=False),
        sa.Column("llm_time_ms", sa.Integer(), nullable=False),
        sa.Column("tool_time_ms", sa.Integer(), nullable=True),
        sa.Column("tool_name", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["turn_id"], ["agent_turns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_iterations_turn_id", "agent_iterations", ["turn_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_iterations_turn_id", table_name="agent_iterations")
    op.drop_table("agent_iterations")
    op.drop_index("ix_agent_turns_user_channel", table_name="agent_turns")
    op.drop_index("ix_agent_turns_created_at", table_name="agent_turns")
    op.drop_table("agent_turns")
