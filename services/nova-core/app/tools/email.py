"""Email tool using MS Graph API with hybrid rule+LLM importance classification."""
from __future__ import annotations

import json
import re

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


async def classify_importance(subject: str, sender: str, preview: str) -> bool:
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
        result = await llm.chat([{"role": "user", "content": prompt}])
        reply_content = result.message.get("content", "").strip().lower()
        return "yes" in reply_content
    except Exception:
        # Fallback to conservative True on error
        return True


async def fetch_emails_from_graph(limit: int = 10, unread_only: bool = False) -> list[dict]:
    token = await _get_access_token()
    
    # Mock data fallback for development if credentials are not configured
    if not token or not settings.azure_mailbox_email:
        return [
            {"id": "msg_1", "subject": "School update: upcoming holidays", "from": "school@edu.nl", "preview": "Dear parents, please note that summer holidays start next week.", "unread": True},
            {"id": "msg_2", "subject": "Radiale CalDAV Server Update", "from": "admin@local.lan", "preview": "The local radicale container has updated successfully.", "unread": False},
            {"id": "msg_3", "subject": "Factuur July 2026", "from": "billing@energy.nl", "preview": "Your monthly energy invoice is ready for download.", "unread": True},
            {"id": "msg_4", "subject": "Spam Offer: Cheap vacations", "from": "spam@deals.com", "preview": "Click here to win a free trip to Hawaii!", "unread": True}
        ]
        
    url = f"https://graph.microsoft.com/v1.0/users/{settings.azure_mailbox_email}/messages"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "$top": limit,
        "$select": "id,subject,from,bodyPreview,isRead,receivedDateTime",
        "$orderby": "receivedDateTime desc"
    }
    if unread_only:
        params["$filter"] = "isRead eq false"
        
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            print(f"[ERROR] Failed to fetch emails: {resp.text}")
            return []
        
        raw_emails = resp.json().get("value", [])
        emails = []
        for item in raw_emails:
            sender_info = item.get("from", {}).get("emailAddress", {})
            emails.append({
                "id": item.get("id"),
                "subject": item.get("subject", "No Subject"),
                "from": f"{sender_info.get('name', '')} <{sender_info.get('address', '')}>",
                "preview": item.get("bodyPreview", ""),
                "unread": not item.get("isRead", True)
            })
        return emails


async def extract_actions_from_email(email: dict) -> list[dict]:
    """Extract actionable items from an email using local LLM.

    Returns a list of action dicts, each with:
      - type: "task" | "event"
      - summary: str
      - due_at: str (ISO date, for tasks) | start/end: str (ISO datetime, for events)
      - confidence: float (0-1)

    Returns empty list if no actions detected or on error.
    """
    prompt = (
        "You are a household email assistant. Extract any actionable items from this email. "
        "Return a JSON array of objects with fields: type ('task' or 'event'), summary, "
        "due_at (for tasks), start/end (for events, ISO format), and confidence (0-1).\n\n"
        f"Subject: {email.get('subject', '')}\n"
        f"From: {email.get('from', '')}\n"
        f"Body: {email.get('preview', email.get('body', ''))}\n\n"
        "If no actionable items exist, return an empty array []."
    )
    try:
        result = await llm.chat([{"role": "user", "content": prompt}])
        content = result.message.get("content", "").strip()
        # Extract JSON array from LLM response
        match = re.search(r'\[.*?\]', content, re.DOTALL)
        if match:
            actions = json.loads(match.group())
            if isinstance(actions, list):
                return actions
        return []
    except Exception as e:
        print(f"[ERROR] extract_actions_from_email failed: {e}")
        return []


async def draft_reply(email: dict) -> str:
    """Generate a reply draft for an email using local LLM.

    Returns the draft text as a string, or empty string on error.
    """
    prompt = (
        "Draft a polite reply to this email. Keep it concise and natural.\n\n"
        f"From: {email.get('from', '')}\n"
        f"Subject: {email.get('subject', '')}\n"
        f"Body: {email.get('preview', email.get('body', ''))}\n\n"
        "Reply draft:"
    )
    try:
        result = await llm.chat([{"role": "user", "content": prompt}])
        draft = result.message.get("content", "").strip()
        return draft
    except Exception as e:
        print(f"[ERROR] draft_reply failed: {e}")
        return ""


@tool(
    name="extract_actions_from_email",
    description="Analyze an email and extract actionable items: tasks or calendar events. Returns proposed tasks/events that the user can confirm.",
    parameters={
        "type": "object",
        "properties": {
            "email_id": {"type": "string", "description": "The email ID from list_recent_emails to analyze."},
        },
        "required": ["email_id"],
    },
)
async def extract_actions_tool(email_id: str) -> str:
    """Tool wrapper — fetches email content and extracts actions."""
    emails = await fetch_emails_from_graph(limit=10)
    email = next((e for e in emails if e["id"] == email_id), None)
    if not email:
        return f"Email with ID '{email_id}' not found."
    actions = await extract_actions_from_email(email)
    if not actions:
        return "No actionable items found in this email."
    lines = []
    for a in actions:
        if a["type"] == "task":
            lines.append(f"📋 Task: {a['summary']} (due: {a.get('due_at', 'unknown')})")
        elif a["type"] == "event":
            lines.append(f"📅 Event: {a['summary']} ({a.get('start', '?')} → {a.get('end', '?')})")
        lines.append(f"   Confidence: {a.get('confidence', 0):.0%}")
    return "Extracted actions:\n" + "\n".join(lines)


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
    emails = await fetch_emails_from_graph(limit=limit, unread_only=unread_only)
    if not emails:
        return "No recent emails."
        
    lines = []
    for i, mail in enumerate(emails, 1):
        subject = mail["subject"]
        sender = mail["from"]
        preview = mail["preview"]
        
        is_important = await classify_importance(subject, sender, preview)
        importance_tag = " [IMPORTANT]" if is_important else ""
        unread_tag = " (Unread)" if mail["unread"] else ""
        
        lines.append(f"{i}. From: {sender}\n   Subject: {subject}{importance_tag}{unread_tag}\n   Preview: {preview}\n")
        
    scope = "unread " if unread_only else ""
    return f"Recent {scope}emails in shared mailbox:\n\n" + "\n".join(lines)
