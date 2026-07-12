"""Outbound message dispatcher — routes sends to the user's last-active channel.

All proactive pushes (briefings, reminders, email alerts) route through
this module instead of calling a channel-specific send function directly.
"""
from __future__ import annotations

from ..db import get_pool


async def send_to_user(user_name: str, text: str, proactive: bool = True) -> None:
    """Send an outbound message to a user on their last-active channel.

    Resolves the user's last_active_channel from user_preferences and
    delegates to the correct ChannelAdapter. Falls back to WhatsApp if
    the user's last-active channel is Telegram but no Telegram identity
    exists.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT up.last_active_channel
            FROM user_preferences up
            JOIN users u ON up.user_id = u.id
            WHERE u.name = $1
            """,
            user_name
        )
        if not row:
            print(f"[ERROR] No preferences found for {user_name}, cannot send")
            return
        last_channel = row["last_active_channel"] or "whatsapp"

    if last_channel == "telegram":
        async with pool.acquire() as conn:
            has_telegram = await conn.fetchval(
                "SELECT 1 FROM channel_identities WHERE channel = 'telegram' AND user_id = (SELECT id FROM users WHERE name = $1)",
                user_name
            )
        if has_telegram:
            from .telegram import adapter as telegram_adapter
            await telegram_adapter.send_message(user_name, text, proactive)
            return
        else:
            print(f"[DISPATCH] {user_name} has last_active=telegram but no Telegram identity — falling back to WhatsApp")

    from .whatsapp import adapter as whatsapp_adapter
    await whatsapp_adapter.send_message(user_name, text, proactive)
