"""Telegram channel adapter — Bot API integration.

Implements ChannelAdapter for the Telegram channel.
Also exports module-level send_telegram_message and process_incoming_telegram
for backward compatibility with scheduler and existing test patterns.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI

# Runtime imports used by register_webhooks (imported at module level so FastAPI
# can resolve type annotations even with `from __future__ import annotations`)
from fastapi import Request, BackgroundTasks, HTTPException

import httpx

from ..agent import run_agent
from ..config import settings
from ..db import get_pool
from ..identity import user_from_telegram, is_user_in_dnd, User, HOUSEHOLD
from ..security import verify_telegram_signature
from . import ChannelAdapter, InboundMessage


def _chunk_message(text: str, max_length: int = 4096) -> list[str]:
    """Split a message into chunks at paragraph boundaries, respecting max_length.

    Falls back to sentence boundaries for paragraphs that exceed max_length.
    Hard-truncates any segment that still exceeds max_length after sentence splitting.
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    paragraphs = text.split("\n\n")
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= max_length:
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para
        else:
            if current_chunk:
                chunks.append(current_chunk)
            if len(para) > max_length:
                sentences = para.replace(". ", ".\n").replace("! ", "!\n").replace("? ", "?\n").split("\n")
                current_chunk = ""
                for sentence in sentences:
                    if len(sentence) > max_length:
                        if current_chunk:
                            chunks.append(current_chunk)
                        chunks.append(sentence[:max_length])
                        current_chunk = sentence[max_length:]
                    elif len(current_chunk) + len(sentence) + 1 <= max_length:
                        if current_chunk:
                            current_chunk += " " + sentence
                        else:
                            current_chunk = sentence
                    else:
                        if current_chunk:
                            chunks.append(current_chunk)
                        current_chunk = sentence
            else:
                current_chunk = para

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def _handle_telegram_command(text: str) -> str:
    """Handle Telegram bot commands. Returns the reply text.

    Moved from main.py in Phase 20.
    """
    cmd = text.split()[0].lower()
    if cmd == "/help":
        return (
            "\U0001f916 I'm Nova, your household assistant.\n\n"
            "I can help with:\n"
            "\U0001f4cb Tasks — add, list, complete household tasks\n"
            "\U0001f4c5 Calendar — check your schedule and events\n"
            "\U0001f4e8 Email — get important email notifications\n"
            "\u23f0 Briefings — morning and weekly summaries\n\n"
            "Just ask me anything! For example:\n"
            '• "What\'s on my calendar today?"\n'
            '• "Add milk to the shopping list"\n'
            '• "What tasks are overdue?"\n\n'
            "Commands:\n"
            "/help — Show this message\n"
            "/tasks — Show your current tasks\n"
            "/settings — Manage your preferences"
        )
    elif cmd == "/tasks":
        return "Task management coming soon. Try asking 'What are my tasks?' in the meantime."
    elif cmd == "/settings":
        return "Preferences management coming soon. Use the web dashboard to adjust your settings."
    return f"Unknown command: {cmd}. Try /help."


class TelegramAdapter(ChannelAdapter):
    """Telegram channel via Bot API."""

    async def register_webhooks(self, app: FastAPI) -> None:
        """Register POST /webhooks/telegram on the FastAPI app (migrated from main.py in Phase 20).

        The inner handler is uniquely named to avoid FastAPI route name collisions
        when register_webhooks is called, and uses name='telegram_webhook' on the
        route decorator for the same reason.
        """
        import json

        @app.post("/webhooks/telegram", name="telegram_webhook")
        async def telegram_webhook_handler(request: Request, background_tasks: BackgroundTasks) -> dict:
            if not settings.nova_telegram_enabled:
                raise HTTPException(status_code=404, detail="Telegram channel is not enabled")

            body = await request.body()
            secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")

            if not verify_telegram_signature(secret_token, settings.telegram_webhook_secret):
                raise HTTPException(status_code=401, detail="Invalid secret token")

            try:
                payload = json.loads(body)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON body")

            update = payload if isinstance(payload, dict) else {}
            msg = update.get("message", {})
            text = msg.get("text", "")
            chat = msg.get("chat", {})
            chat_id = str(chat.get("id", ""))

            if text and chat_id:
                update_id = update.get("update_id")
                if update_id is not None:
                    pool = await get_pool()
                    async with pool.acquire() as conn:
                        result = await conn.execute(
                            "INSERT INTO processed_telegram_updates (update_id) VALUES ($1) ON CONFLICT (update_id) DO NOTHING",
                            update_id
                        )
                        if result != "INSERT 0 1":
                            return {"status": "accepted"}

                if text.startswith("/"):
                    reply = _handle_telegram_command(text)
                    background_tasks.add_task(send_telegram_message, chat_id, reply)
                else:
                    background_tasks.add_task(process_incoming_telegram, payload)

            return {"status": "accepted"}

    async def send_message(self, user_name: str, text: str, proactive: bool = False) -> None:
        """ChannelAdapter.send_message: resolve user_name to chat_id, then send."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT ci.channel_id FROM channel_identities ci
                JOIN users u ON ci.user_id = u.id
                WHERE u.name = $1 AND ci.channel = 'telegram'
                """,
                user_name
            )
            if not row or not row["channel_id"]:
                print(f"[ERROR] No Telegram chat_id for {user_name}, cannot send")
                return
            chat_id = row["channel_id"]
        await _send_to_chat_id(chat_id, text, proactive, user_name)

    async def process_incoming(self, raw_payload: Any) -> InboundMessage | None:
        """Parse a validated Telegram Update into an InboundMessage.

        Returns None for non-message updates, commands, edited messages, etc.
        """
        try:
            update = raw_payload if isinstance(raw_payload, dict) else {}
            if "message" not in update:
                return None
            msg = update["message"]
            chat = msg.get("chat", {})
            chat_id = chat.get("id")
            text = msg.get("text", "")
            if not chat_id or not text:
                return None
            if text.startswith("/"):
                return None
        except (KeyError, TypeError):
            return None

        return InboundMessage(
            channel="telegram",
            sender_id=str(chat_id),
            text=text,
            raw_payload=raw_payload
        )


async def _send_to_chat_id(chat_id: str, text: str, proactive: bool, user_name: str | None = None) -> None:
    """Core send logic — checks DND, sends via Bot API.

    Telegram does not have a 24h compliance window (unlike WhatsApp),
    so DND is the only gate for proactive messages.
    """
    if user_name:
        user = User(name=user_name)
    else:
        user = await user_from_telegram(chat_id)

    if proactive and user.name != "household":
        if await is_user_in_dnd(user.name):
            print(f"[DND ACTIVE] Suppressing Telegram proactive message for {user.name} ({chat_id})")
            return

    if not settings.telegram_bot_token:
        print(f"[MOCK TELEGRAM OUTBOUND] To: {chat_id}, Body: {text}")
        return

    chunks = _chunk_message(text)
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient() as client:
        for i, chunk in enumerate(chunks):
            payload = {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML",
            }
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                print(f"[ERROR] Telegram API replied {resp.status_code}: {resp.text}")
            if i < len(chunks) - 1:
                await asyncio.sleep(1)


async def send_telegram_message(chat_id: str, text: str, proactive: bool = False):
    """Send message to a Telegram chat_id (backward-compat)."""
    await _send_to_chat_id(chat_id, text, proactive, user_name=None)


async def process_incoming_telegram(payload: dict):
    """Background task processing validated incoming Telegram updates."""
    try:
        update = payload if isinstance(payload, dict) else {}
        msg = update.get("message", {})
        chat = msg.get("chat", {})
        chat_id = str(chat.get("id", ""))
        text = msg.get("text", "")
        if not chat_id or not text:
            return
        if text.startswith("/"):
            return
    except Exception:
        return

    user = await user_from_telegram(chat_id)
    if user == HOUSEHOLD:
        await _send_to_chat_id(chat_id, "Sorry, you are not authorized to use this household assistant.", proactive=False)
        return

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE users SET last_inbound_at = now() WHERE name = $1", user.name)
            await conn.execute(
                "UPDATE user_preferences SET last_active_channel = 'telegram' WHERE user_id = (SELECT id FROM users WHERE name = $1)",
                user.name
            )
    except Exception as e:
        print(f"[ERROR] Failed to update last_inbound_at: {e}")

    reply = await run_agent(text, user=user.name, channel="telegram")
    await _send_to_chat_id(chat_id, reply, proactive=False, user_name=user.name)


async def send_telegram_otp(user_name: str, code: str) -> bool:
    """Send a 6-digit OTP verification code to a user's Telegram DM.

    Resolves the household member's name to their Telegram chat_id via
    channel_identities, then dispatches the code via _send_to_chat_id.

    Returns True if the chat_id was found and the send was dispatched.
    Returns False if no chat_id is linked for the given user.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT ci.channel_id FROM channel_identities ci
            JOIN users u ON ci.user_id = u.id
            WHERE u.name = $1 AND ci.channel = 'telegram'
            """,
            user_name
        )
        if not row or not row["channel_id"]:
            print(f"[ERROR] No Telegram chat_id for {user_name}, cannot send OTP")
            return False
        chat_id = row["channel_id"]

    message_text = f"Your Nova verification code is: {code}. It expires in 5 minutes."
    await _send_to_chat_id(chat_id, message_text, proactive=False, user_name=user_name)
    print(f"[OTP SENT] Telegram OTP to {user_name} (chat_id: {chat_id})")
    return True


adapter = TelegramAdapter()
