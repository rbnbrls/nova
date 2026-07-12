"""WhatsApp adapter for Meta Cloud API integration."""
from __future__ import annotations

from datetime import datetime, timezone
import httpx

from .agent import run_agent
from .config import settings
from .db import get_pool
from .identity import user_from_whatsapp


async def send_whatsapp_message(to_number: str, text: str):
    """Send message response back to the user via Meta Cloud API, checking 24h compliance."""
    if not settings.whatsapp_phone_number_id or not settings.whatsapp_access_token:
        # Mock/log during development if config is missing
        print(f"[MOCK WHATSAPP OUTBOUND] To: {to_number}, Body: {text}")
        return

    # Check 24-hour compliance window
    user = await user_from_whatsapp(to_number)
    is_template = True
    if user.name != "household":
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow("SELECT last_inbound_at FROM users WHERE name = $1", user.name)
                if row and row["last_inbound_at"]:
                    diff = datetime.now(timezone.utc) - row["last_inbound_at"]
                    if diff.total_seconds() < 24 * 3600:
                        is_template = False
        except Exception as e:
            # Fallback to template if DB is unreachable
            print(f"[WARNING] DB error checking last_inbound_at, defaulting to template: {e}")

    url = f"https://graph.facebook.com/v18.0/{settings.whatsapp_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }
    
    if is_template:
        # Construct pre-approved template payload
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
                            {"type": "text", "text": text}
                        ]
                    }
                ]
            }
        }
    else:
        # Construct plain text payload
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


async def process_incoming_whatsapp(payload: dict):
    """Background task processing validated incoming webhook messages."""
    try:
        entry = payload.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return  # Not a message delivery event
            
        msg = messages[0]
        sender = msg.get("from")
        text = msg.get("text", {}).get("body")
        if not sender or not text:
            return
    except Exception:
        return

    from . import identity
    clean_sender = sender.lstrip("+")
    # Resolve sender user name
    user = await identity.user_from_whatsapp(clean_sender)
    if user == identity.HOUSEHOLD:
        # Refusal policy: Instantly reply with standard message, skip LLM
        await send_whatsapp_message(sender, "Sorry, you are not authorized to use this household assistant.")
        return

    # Update last_inbound_at in database
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET last_inbound_at = now() WHERE name = $1",
                user.name
            )
    except Exception as e:
        print(f"[ERROR] Failed to update last_inbound_at: {e}")
    
    # Execute agent loop
    reply = await run_agent(text, user=user.name)
    
    # Send reply
    await send_whatsapp_message(sender, reply)
