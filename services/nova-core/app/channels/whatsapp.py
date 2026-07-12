"""WhatsApp channel adapter — Meta Cloud API integration.

Implements ChannelAdapter for the WhatsApp channel.
Also exports module-level send_whatsapp_message and process_incoming_whatsapp
for backward compatibility with scheduler and existing test patches.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI
import httpx

from ..agent import run_agent
from ..config import settings
from ..db import get_pool
from ..feedback import detect_feedback_reaction, feedback_context, file_feedback_issue  # D-01, D-02, D-03
from ..identity import user_from_whatsapp
from . import ChannelAdapter, InboundMessage


def _parse_reaction(payload: dict) -> dict | None:
    """Extract reaction info from a WhatsApp webhook payload.

    Returns dict with keys {from, message_id, emoji, channel} or None
    if the payload is not a reaction message.

    Per D-01: reactions are detected before normal message processing.
    """
    try:
        entry = payload.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return None
        msg = messages[0]
        if msg.get("type") != "reaction":
            return None
        reaction = msg.get("reaction", {})
        if not reaction.get("emoji"):
            return None
        return {
            "from": msg.get("from", "").lstrip("+"),
            "message_id": reaction.get("message_id", ""),
            "emoji": reaction.get("emoji", ""),
            "channel": "whatsapp",
        }
    except (IndexError, KeyError, TypeError):
        return None


class WhatsAppAdapter(ChannelAdapter):
    """WhatsApp channel via Meta Cloud API."""

    async def register_webhooks(self, app: FastAPI) -> None:
        """Register webhook routes on the FastAPI application.

        Webhook routes are registered in main.py at /webhooks/whatsapp.
        Route migration to adapter method deferred to Phase 20.
        """
        pass

    async def send_message(self, user_name: str, text: str, proactive: bool = False) -> None:
        """ChannelAdapter.send_message: resolve user_name to number, then send."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT up.whatsapp_number FROM user_preferences up "
                "JOIN users u ON up.user_id = u.id WHERE u.name = $1",
                user_name
            )
            if not row or not row["whatsapp_number"]:
                print(f"[ERROR] No WhatsApp number for {user_name}, cannot send")
                return
            to_number = row["whatsapp_number"]
        await _send_to_number(to_number, text, proactive, user_name)

    async def process_incoming(self, raw_payload: Any) -> InboundMessage | None:
        """Parse a validated webhook payload into an InboundMessage.

        Returns None for non-message events (status updates, echoes).
        Handles both text and image message types.
        """
        try:
            entry = raw_payload.get("entry", [])[0]
            change = entry.get("changes", [])[0]
            value = change.get("value", {})
            messages = value.get("messages", [])
            if not messages:
                return None
            msg = messages[0]
            sender = msg.get("from", "")
            text = msg.get("text", {}).get("body", "")
            # Detect image messages (WhatsApp sends no text body for images)
            media_type = "image" if msg.get("image") else None
            media_id = msg.get("image", {}).get("id") if media_type else None
            if not sender:
                return None
            if not text and not media_id:
                return None  # Not a text or image message — status update, echo, etc.
        except (IndexError, KeyError, TypeError):
            return None

        return InboundMessage(
            channel="whatsapp",
            sender_id=sender.lstrip("+"),
            text=text or "",
            media_type=media_type,
            media_id=media_id,
            raw_payload=raw_payload,
        )


async def _send_to_number(to_number: str, text: str, proactive: bool, user_name: str | None = None) -> None:
    """Core send logic — checks DND, 24h compliance, sends via Meta API."""
    if user_name:
        from ..identity import User
        user = User(name=user_name)
    else:
        user = await user_from_whatsapp(to_number)

    if proactive and user.name != "household":
        from ..identity import is_user_in_dnd
        if await is_user_in_dnd(user.name):
            print(f"[DND ACTIVE] Queuing proactive message for {user.name} ({to_number})")
            try:
                pool = await get_pool()
                async with pool.acquire() as conn:
                    user_id = await conn.fetchval("SELECT id FROM users WHERE name = $1", user.name)
                    if user_id:
                        await conn.execute(
                            """INSERT INTO queued_notifications (user_id, whatsapp_number, message_text, channel)
                               VALUES ($1, $2, $3, 'whatsapp')""",
                            user_id, to_number.lstrip("+"), text
                        )
            except Exception as e:
                print(f"[ERROR] Failed to queue notification during DND: {e}")
            return

    if not settings.whatsapp_phone_number_id or not settings.whatsapp_access_token:
        print(f"[MOCK WHATSAPP OUTBOUND] To: {to_number}, Body: {text}")
        return

    # 24h compliance check
    is_template = True
    if user.name != "household":
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT last_inbound_at FROM users WHERE name = $1", user.name
                )
                if row and row["last_inbound_at"]:
                    diff = datetime.now(timezone.utc) - row["last_inbound_at"]
                    if diff.total_seconds() < 24 * 3600:
                        is_template = False
        except Exception as e:
            print(f"[WARNING] DB error checking last_inbound_at, defaulting to template: {e}")

    url = f"https://graph.facebook.com/v18.0/{settings.whatsapp_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }

    if is_template:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "template",
            "template": {
                "name": "household_update",
                "language": {"code": "en"},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": text},
                        ],
                    },
                ],
            },
        }
    else:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code not in (200, 201):
            print(f"[ERROR] Meta API replied {resp.status_code}: {resp.text}")


async def send_whatsapp_otp(to_number: str, code: str) -> None:
    """Send a one-time verification code via Meta's whatsapp_authentication template.

    Uses the pre-approved AUTHENTICATION category template that Meta provides
    to all WhatsApp Business Accounts. On Meta API failure, raises RuntimeError
    so the caller can surface a user-facing retry option.
    """
    clean_number = to_number.lstrip("+")

    if not settings.whatsapp_phone_number_id or not settings.whatsapp_access_token:
        print(f"[MOCK WHATSAPP OTP] To: {clean_number}, Code: {code}")
        return

    url = f"https://graph.facebook.com/v18.0/{settings.whatsapp_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": clean_number,
        "type": "template",
        "template": {
            "name": "whatsapp_authentication",
            "language": {"code": "en"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": code},
                    ],
                },
            ],
        },
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code in (200, 201):
            print(f"[OTP SENT] To: {clean_number}")
        else:
            print(f"[OTP FAILED] To: {clean_number}, Status: {resp.status_code}, Response: {resp.text}")
            raise RuntimeError(
                f"Failed to send OTP to {clean_number}: Meta API returned {resp.status_code}"
            )


async def send_whatsapp_message(to_number: str, text: str, proactive: bool = False):
    """Send message response back to the user via Meta Cloud API (backward-compat)."""
    await _send_to_number(to_number, text, proactive, user_name=None)


async def download_whatsapp_media(media_id: str) -> bytes | None:
    """Download image bytes from Meta's media servers via the Graph API.

    Args:
        media_id: Media ID from the WhatsApp image payload (msg.image.id).

    Returns:
        Raw image bytes on success, None on any failure (with logging).
    """
    if not settings.whatsapp_access_token:
        print(f"[MOCK DOWNLOAD] Media {media_id} — token not configured, returning None")
        return None

    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    media_url = f"https://graph.facebook.com/v18.0/{media_id}"

    try:
        async with httpx.AsyncClient() as client:
            # Step 1: Resolve media ID to a temporary download URL
            resp = await client.get(media_url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            download_url = data.get("url")
            if not download_url:
                print(f"[ERROR] Meta API response for media {media_id} has no 'url' field: {data}")
                return None

            # Step 2: Download the actual image bytes
            dl_resp = await client.get(download_url, headers=headers)
            dl_resp.raise_for_status()
            return dl_resp.content
    except httpx.HTTPStatusError as e:
        print(f"[ERROR] Meta API HTTP error downloading media {media_id}: {e}")
        return None
    except httpx.RequestError as e:
        print(f"[ERROR] Network error downloading media {media_id}: {e}")
        return None
    except Exception as e:
        print(f"[ERROR] Unexpected error downloading media {media_id}: {e}")
        return None


async def process_incoming_whatsapp(payload: dict):
    """Background task processing validated incoming webhook messages (backward-compat).

    Handles both text and image messages. Image messages are downloaded from Meta,
    analyzed via the local vision model, and the extraction context is piped into
    the agent as a synthetic user message.

    Also handles WhatsApp reaction messages (👎) — files a feedback issue
    without running the agent loop.
    """
    # FEEDBACK-01: Detect WhatsApp reactions before normal message processing
    # per D-01: thumbs-down reaction triggers feedback issue filing
    reaction_info = _parse_reaction(payload)
    if reaction_info is not None:
        if detect_feedback_reaction(reaction_info["emoji"]):
            sender = reaction_info["from"]
            from .. import identity
            user = await identity.user_from_whatsapp(sender)
            if user.name != "household":
                ctx = feedback_context.get(user.name)
                trigger = f"reaction: 👎 on message {reaction_info['message_id'][:20]}"
                asyncio.create_task(file_feedback_issue(user.name, "whatsapp", ctx, trigger))
            else:
                print(f"[FEEDBACK] Reaction from unrecognized sender {sender} — skipped")
        return

    # Use the adapter to parse the payload (handles both text and image)
    adapter = WhatsAppAdapter()
    inbound = await adapter.process_incoming(payload)
    if inbound is None:
        return

    sender = inbound.sender_id
    text = inbound.text
    media_id = inbound.media_id

    from .. import identity
    clean_sender = sender.lstrip("+")
    user = await identity.user_from_whatsapp(clean_sender)
    if user == identity.HOUSEHOLD:
        await send_whatsapp_message(sender, "Sorry, you are not authorized to use this household assistant.")
        return

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE users SET last_inbound_at = now() WHERE name = $1", user.name)
            await conn.execute(
                "UPDATE user_preferences SET last_active_channel = 'whatsapp' WHERE user_id = (SELECT id FROM users WHERE name = $1)",
                user.name
            )
    except Exception as e:
        print(f"[ERROR] Failed to update last_inbound_at: {e}")

    # Image message handling: download → analyze → build synthetic context
    if media_id:
        image_bytes = await download_whatsapp_media(media_id)
        if image_bytes:
            from app.vision import analyze_image
            extraction = await analyze_image(image_bytes)
            if extraction.get("error"):
                await send_whatsapp_message(
                    sender,
                    "I had trouble reading that photo. Could you type the important details instead?"
                )
                return

            # Build a synthetic message so the LLM can reason about the extraction
            text = (
                f"[User sent a photo. Vision analysis: {extraction.get('summary', '')}\n"
                f" Extracted events: {extraction.get('events', [])}  "
                f"Extracted tasks: {extraction.get('tasks', [])}]"
            )
        else:
            await send_whatsapp_message(
                sender,
                "I could not download the photo you sent. Please try again or send the text directly."
            )
            return

    reply = await run_agent(text, user=user.name, channel="whatsapp")
    await send_whatsapp_message(sender, reply)


adapter = WhatsAppAdapter()
