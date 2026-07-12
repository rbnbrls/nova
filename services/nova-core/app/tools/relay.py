"""Message relay tool — let household members send messages to each other.

Relays a message from one household member to another via the dispatcher,
which routes to the recipient's last-active channel (WhatsApp or Telegram).
"""
from __future__ import annotations

from .base import tool
from ..db import get_pool
from ..channels.dispatcher import send_to_user


@tool(
    name="relay_message",
    description="Relay a message to another household member on their preferred channel. "
                "Use this when someone wants to send a quick note to their partner.",
    parameters={
        "type": "object",
        "properties": {
            "recipient": {
                "type": "string",
                "description": "Name of the household member to relay the message to, e.g. 'Meral' or 'Ruben'.",
            },
            "message": {
                "type": "string",
                "description": "The message content to relay.",
            },
        },
        "required": ["recipient", "message"],
    },
)
async def relay_message(recipient: str, message: str, user: str) -> str:
    # Prevent self-relay
    if recipient.lower() == user.lower():
        return "You cannot relay a message to yourself."

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Validate recipient exists in users table
        recipient_row = await conn.fetchrow(
            "SELECT id FROM users WHERE name = $1",
            recipient,
        )
        if not recipient_row:
            return f"Could not find user '{recipient}'."

    # Deliver via dispatcher with sender attribution
    formatted = f"📩 From {user}: {message}"
    await send_to_user(recipient, formatted, proactive=False)

    return f"Message relayed to {recipient}."
