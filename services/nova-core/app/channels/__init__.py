"""Channel adapter interface and shared types.

Every channel (WhatsApp, Telegram, voice) implements ChannelAdapter.
InboundMessage normalises incoming payloads into a common shape.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI


@dataclass
class InboundMessage:
    """Normalised representation of an incoming channel message."""

    channel: str              # 'whatsapp' | 'telegram' | 'voice'
    sender_id: str            # Channel-specific sender identifier (E.164, chat_id, etc.)
    text: str                 # Message body text
    raw_payload: Any          # Original payload for channel-specific access
    media_type: str | None = None   # 'image' for photo messages, None for text
    media_id: str | None = None     # Channel-specific media identifier (e.g. WhatsApp image.id)


class ChannelAdapter(ABC):
    """Interface for inbound + outbound message handling on a single channel.

    Each channel adapter:
      - Registers any webhook routes on the FastAPI app
      - Parses incoming payloads into InboundMessage
      - Sends outbound messages via the channel's API
    """

    @abstractmethod
    async def register_webhooks(self, app: FastAPI) -> None:
        """Register webhook routes on the FastAPI application.

        Each channel adapter defines its own webhook route(s) under /webhooks/*
        and attaches them to the provided FastAPI app instance. The method is
        called during application startup.

        Args:
            app: The FastAPI application instance to attach routes to.
        """
        ...

    @abstractmethod
    async def send_message(self, user_name: str, text: str, proactive: bool = False) -> None:
        """Send an outbound message to a user on this channel.

        Args:
            user_name: Household user name (e.g. 'Ruben', 'Meral').
            text: Message body to send.
            proactive: If True, the message may require template compliance
                       or DND gating depending on channel rules.
        """
        ...

    @abstractmethod
    async def process_incoming(self, raw_payload: Any) -> InboundMessage | None:
        """Parse a validated incoming payload into an InboundMessage.

        Returns None if the payload is not a user message
        (e.g. status update, echo, delivery receipt).
        """
        ...
