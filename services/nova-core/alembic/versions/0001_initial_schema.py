"""Create initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )

    if "tasks" not in tables:
        op.create_table(
            "tasks",
            sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),
            sa.Column("assignee_id", sa.UUID(), nullable=True),
            sa.Column("created_by", sa.UUID(), nullable=True),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], ),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("tasks_active_due_idx", "tasks", ["due_at"], postgresql_where=sa.text("status = 'active'"))

    if "memories" not in tables:
        op.create_table(
            "memories",
            sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ),
            sa.PrimaryKeyConstraint("id"),
        )

    if "messages" not in tables:
        op.create_table(
            "messages",
            sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=True),
            sa.Column("channel", sa.Text(), nullable=False),
            sa.Column("role", sa.Text(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("messages_user_channel_idx", "messages", ["user_id", "channel", sa.text("created_at DESC")])

    if "user_preferences" not in tables:
        op.create_table(
            "user_preferences",
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column("whatsapp_number", sa.Text(), nullable=True),
            sa.Column("dnd_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=True),
            sa.Column("dnd_start", sa.Time(), server_default=sa.text("'22:00:00'"), nullable=True),
            sa.Column("dnd_end", sa.Time(), server_default=sa.text("'07:00:00'"), nullable=True),
            sa.Column("morning_briefing_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=True),
            sa.Column("morning_briefing_time", sa.Time(), server_default=sa.text("'07:00:00'"), nullable=True),
            sa.Column("weekly_briefing_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=True),
            sa.Column("weekly_briefing_day", sa.Integer(), server_default=sa.text("1"), nullable=True),
            sa.Column("weekly_briefing_time", sa.Time(), server_default=sa.text("'09:00:00'"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("last_active_channel", sa.Text(), server_default=sa.text("'whatsapp'"), nullable=False),
            sa.Column("channels_enabled", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{whatsapp}'"), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("user_id"),
            sa.UniqueConstraint("whatsapp_number"),
        )

    if "whatsapp_verification_codes" not in tables:
        op.create_table(
            "whatsapp_verification_codes",
            sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column("whatsapp_number", sa.Text(), nullable=False),
            sa.Column("code", sa.Text(), nullable=False),
            sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if "queued_notifications" not in tables:
        op.create_table(
            "queued_notifications",
            sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column("whatsapp_number", sa.Text(), nullable=True),
            sa.Column("message_text", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("channel", sa.Text(), server_default=sa.text("'whatsapp'"), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if "channel_verification_codes" not in tables:
        op.create_table(
            "channel_verification_codes",
            sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column("whatsapp_number", sa.Text(), nullable=False),
            sa.Column("code", sa.Text(), nullable=False),
            sa.Column("channel", sa.Text(), server_default=sa.text("'whatsapp'"), nullable=False),
            sa.Column("channel_id", sa.Text(), nullable=True),
            sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if "channel_identities" not in tables:
        op.create_table(
            "channel_identities",
            sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column("channel", sa.Text(), nullable=False),
            sa.Column("channel_id", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("channel_identities_unique_idx", "channel_identities", ["channel", "channel_id"], unique=True)

    if "processed_telegram_updates" not in tables:
        op.create_table(
            "processed_telegram_updates",
            sa.Column("update_id", sa.BigInteger(), nullable=False),
            sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("update_id"),
        )


def downgrade() -> None:
    op.drop_table("processed_telegram_updates")
    op.drop_table("channel_identities")
    op.drop_table("channel_verification_codes")
    op.drop_table("queued_notifications")
    op.drop_table("whatsapp_verification_codes")
    op.drop_table("user_preferences")
    op.drop_table("messages")
    op.drop_table("memories")
    op.drop_table("tasks")
    op.drop_table("users")
