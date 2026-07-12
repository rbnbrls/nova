"""WhatsApp channel adapter — Meta Cloud API integration.

Implements ChannelAdapter for the WhatsApp channel.
Also exports module-level send_whatsapp_message and process_incoming_whatsapp
for backward compatibility with scheduler and existing test patches.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import httpx

from ..agent import run_agent
from ..config import settings
from ..db import get_pool
from ..identity import user_from_whatsapp
from . import ChannelAdapter, InboundMessage


class WhatsAppAdapter(ChannelAdapter):
    """WhatsApp channel via Meta Cloud API."""

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
            if not sender or not text:
                return None
        except (IndexError, KeyError, TypeError):
            return None

        return InboundMessage(
            channel="whatsapp",
            sender_id=sender.lstrip("+"),
            text=text,
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


async def process_incoming_whatsapp(payload: dict):
    """Background task processing validated incoming webhook messages (backward-compat)."""
    try:
        entry = payload.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return
        msg = messages[0]
        sender = msg.get("from")
        text = msg.get("text", {}).get("body")
        if not sender or not text:
            return
    except Exception:
        return

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

    reply = await run_agent(text, user=user.name)
    await send_whatsapp_message(sender, reply)


adapter = WhatsAppAdapter()
