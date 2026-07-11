"""Email tool using MS Graph API with hybrid rule+LLM importance classification."""
from __future__ import annotations

import httpx

from .base import tool
from ..config import settings
from .. import llm

# Whitelisted keywords indicating an email is important
IMPORTANT_KEYWORDS = [
    "factuur", "invoice", "payment", "betaling", "belangrijk", "important",
    "urgent", "dringend", "school", "gemeente", "belasting", "tax", "dentist",
    "tandarts", "appointment", "afspraak", "bevestiging", "confirmation"
]


async def _get_access_token() -> str | None:
    if not all([settings.azure_tenant_id, settings.azure_client_id, settings.azure_client_secret]):
        return None
        
    url = f"https://login.microsoftonline.com/{settings.azure_tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": settings.azure_client_id,
        "scope": "https://graph.microsoft.com/.default",
        "client_secret": settings.azure_client_secret,
        "grant_type": "client_credentials"
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, data=data)
        if resp.status_code == 200:
            return resp.json().get("access_token")
    return None


async def _classify_importance(subject: str, sender: str, preview: str) -> bool:
    # 1. Rules-based pass (check keywords in subject or body preview)
    combined_text = f"{subject} {preview}".lower()
    for kw in IMPORTANT_KEYWORDS:
        if kw in combined_text:
            return True
            
    # 2. Local LLM fallback
    prompt = (
        "You are a household email assistant. Is the following email important enough to alert the family? "
        "Reply with exactly 'Yes' or 'No'.\n\n"
        f"From: {sender}\n"
        f"Subject: {subject}\n"
        f"Preview: {preview}\n"
    )
    try:
        reply = await llm.chat([{"role": "user", "content": prompt}])
        reply_content = reply.get("content", "").strip().lower()
        return "yes" in reply_content
    except Exception:
        # Fallback to conservative True on error
        return True


@tool(
    name="list_recent_emails",
    description="List recent emails from the shared Outlook mailbox, newest first.",
    parameters={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "How many to fetch (default 10)."},
            "unread_only": {"type": "boolean", "description": "Only unread messages."},
        },
    },
)
async def list_recent_emails(limit: int = 10, unread_only: bool = False) -> str:
    token = await _get_access_token()
    
    # Mock data fallback for development if credentials are not configured
    if not token or not settings.azure_mailbox_email:
        emails = [
            {"subject": "School update: upcoming holidays", "from": "school@edu.nl", "preview": "Dear parents, please note that summer holidays start next week.", "unread": True},
            {"subject": "Radiale CalDAV Server Update", "from": "admin@local.lan", "preview": "The local radicale container has updated successfully.", "unread": False},
            {"subject": "Factuur July 2026", "from": "billing@energy.nl", "preview": "Your monthly energy invoice is ready for download.", "unread": True},
            {"subject": "Spam Offer: Cheap vacations", "from": "spam@deals.com", "preview": "Click here to win a free trip to Hawaii!", "unread": True}
        ]
    else:
        url = f"https://graph.microsoft.com/v1.0/users/{settings.azure_mailbox_email}/messages"
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "$top": limit,
            "$select": "subject,from,bodyPreview,isRead,receivedDateTime",
            "$orderby": "receivedDateTime desc"
        }
        if unread_only:
            params["$filter"] = "isRead eq false"
            
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code != 200:
                return f"Error connecting to MS Graph API: {resp.text}"
            
            raw_emails = resp.json().get("value", [])
            emails = []
            for item in raw_emails:
                sender_info = item.get("from", {}).get("emailAddress", {})
                emails.append({
                    "subject": item.get("subject", "No Subject"),
                    "from": f"{sender_info.get('name', '')} <{sender_info.get('address', '')}>",
                    "preview": item.get("bodyPreview", ""),
                    "unread": not item.get("isRead", True)
                })

    lines = []
    for i, mail in enumerate(emails, 1):
        subject = mail["subject"]
        sender = mail["from"]
        preview = mail["preview"]
        
        is_important = await _classify_importance(subject, sender, preview)
        importance_tag = " [IMPORTANT]" if is_important else ""
        unread_tag = " (Unread)" if mail["unread"] else ""
        
        lines.append(f"{i}. From: {sender}\n   Subject: {subject}{importance_tag}{unread_tag}\n   Preview: {preview}\n")
        
    scope = "unread " if unread_only else ""
    return f"Recent {scope}emails in shared mailbox:\n\n" + "\n".join(lines)
