"""Multi-channel identity resolution via channel_identities table.

Resolves (channel, channel_id) to a household user name using the
channel_identities table. This is the canonical resolver for all
channels — replaces per-channel WhatsApp-only resolvers over time.
"""
from __future__ import annotations

from ..db import get_pool
from ..identity import User, HOUSEHOLD


async def resolve(channel: str, channel_id: str) -> User:
    """Resolve a channel-specific identity to a household user.

    Args:
        channel: Channel name ('whatsapp', 'telegram', etc.).
        channel_id: Channel-specific identifier (E.164 number, chat_id, etc.).

    Returns:
        User dataclass (e.g. User(name='Ruben')) or HOUSEHOLD if unknown.
    """
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT u.name
                FROM channel_identities ci
                JOIN users u ON ci.user_id = u.id
                WHERE ci.channel = $1 AND ci.channel_id = $2
                """,
                channel,
                str(channel_id)
            )
            if row:
                return User(name=row["name"])
    except Exception as e:
        print(f"[ERROR] Identity resolution failed for {channel}/{channel_id}: {e}")
    return HOUSEHOLD
