"""Channel webhook registration and routing.

Called at module load time from main.py after app creation.
Iterates over registered channel adapters and calls their
register_webhooks methods to attach webhook routes.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI


async def register_all_webhooks(app: FastAPI) -> None:
    """Register webhook routes for all enabled channel adapters.

    Each adapter's register_webhooks is async (per ChannelAdapter ABC),
    but actual FastAPI route registration is synchronous.
    Called from main.py at module load time after app creation.
    """
    from .telegram import adapter as telegram_adapter

    # TelegramAdapter.register_webhooks registers POST /webhooks/telegram
    await telegram_adapter.register_webhooks(app)

    # WhatsAppAdapter.register_webhooks is a no-op for now;
    # WhatsApp routes remain in main.py for backward compatibility.
    from .whatsapp import adapter as whatsapp_adapter
    await whatsapp_adapter.register_webhooks(app)
