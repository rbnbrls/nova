"""WhatsApp adapter for Meta Cloud API integration."""
from __future__ import annotations

import httpx

from .agent import run_agent
from .config import settings
from .identity import _WHATSAPP_USERS, user_from_whatsapp


async def send_whatsapp_message(to_number: str, text: str):
    """Send text message response back to the user via Meta Cloud API."""
    if not settings.whatsapp_phone_number_id or not settings.whatsapp_access_token:
        # Mock/log during development if config is missing
        print(f"[MOCK WHATSAPP OUTBOUND] To: {to_number}, Body: {text}")
        return

    url = f"https://graph.facebook.com/v18.0/{settings.whatsapp_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }
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

    # E.164 authorization check
    from . import identity
    clean_sender = sender.lstrip("+")
    if clean_sender not in identity._WHATSAPP_USERS:
        # Refusal policy: Instantly reply with standard message, skip LLM
        await send_whatsapp_message(sender, "Sorry, you are not authorized to use this household assistant.")
        return

    # Resolve sender user name
    user = identity.user_from_whatsapp(sender)

    
    # Execute agent loop
    reply = await run_agent(text, user=user.name)
    
    # Send reply
    await send_whatsapp_message(sender, reply)
