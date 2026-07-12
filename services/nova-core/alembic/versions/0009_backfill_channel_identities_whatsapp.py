"""Backfill existing WhatsApp numbers into channel_identities

Copies existing whatsapp_number values from user_preferences into
channel_identities so the unified resolver works for WhatsApp
identities, not just Telegram.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO channel_identities (user_id, channel, channel_id)
        SELECT up.user_id, 'whatsapp', up.whatsapp_number
        FROM user_preferences up
        WHERE up.whatsapp_number IS NOT NULL
        ON CONFLICT (channel, channel_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM channel_identities WHERE channel = 'whatsapp'"
    )
