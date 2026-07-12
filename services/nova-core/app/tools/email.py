"""Email tool using IMAP/SMTP with hybrid rule+LLM importance classification."""
from __future__ import annotations

import json
import re
from email.message import EmailMessage

import aiosmtplib
from aioimaplib import aioimaplib

from .base import tool
from ..config import settings
from .. import llm

# Whitelisted keywords indicating an email is important
IMPORTANT_KEYWORDS = [
    "factuur", "invoice", "payment", "betaling", "belangrijk", "important",
    "urgent", "dringend", "school", "gemeente", "belasting", "tax", "dentist",
    "tandarts", "appointment", "afspraak", "bevestiging", "confirmation"
]


# ---------------------------------------------------------------------------
# IMAP helpers
# ---------------------------------------------------------------------------

async def _get_imap_connection():
    """Create and return a connected aioimaplib.IMAP4_SSL client.

    Returns None if no IMAP host is configured (mock fallback gate).
    """
    if not settings.nova_imap_host:
        return None
    imap = aioimaplib.IMAP4_SSL(
        host=settings.nova_imap_host,
        port=settings.nova_imap_port,
    )
    await imap.wait_hello_from_server()
    await imap.login(settings.nova_imap_user, settings.nova_imap_pass)
    return imap


def _parse_header(msg_data: list, header_name: str) -> str:
    """Extract a header value from IMAP fetch response bytes."""
    header_key = header_name.lower() + ":"
    for item in msg_data:
        if isinstance(item, bytes):
            text = item.decode("utf-8", errors="replace")
            for line in text.split("\r\n"):
                if line.lower().startswith(header_key):
                    return line[len(header_key):].strip()
        elif isinstance(item, tuple):
            # Nested tuple from aioimaplib response
            for sub_item in item:
                if isinstance(sub_item, bytes):
                    text = sub_item.decode("utf-8", errors="replace")
                    for line in text.split("\r\n"):
                        if line.lower().startswith(header_key):
                            return line[len(header_key):].strip()
    return ""


def _parse_flags(msg_data: list) -> list[str]:
    """Extract flag list from IMAP fetch response."""
    for item in msg_data:
        if isinstance(item, (bytes, str)):
            text = item.decode("utf-8", errors="replace") if isinstance(item, bytes) else item
            # Flags look like: ... FLAGS (\Seen \Flagged) ...
            if "FLAGS" in text:
                match = re.search(r"FLAGS\s*\(([^)]*)\)", text)
                if match:
                    return match.group(1).split()
        elif isinstance(item, tuple):
            for sub_item in item:
                if isinstance(sub_item, bytes):
                    text = sub_item.decode("utf-8", errors="replace")
                    if "FLAGS" in text:
                        match = re.search(r"FLAGS\s*\(([^)]*)\)", text)
                        if match:
                            return match.group(1).split()
    return []


async def fetch_emails_imap(limit: int = 10, unread_only: bool = False) -> list[dict]:
    """Fetch emails via IMAP. Returns list of dicts with {id, subject, from, preview, unread}.

    Uses UID-based operations (never message sequence numbers).
    Falls back to mock data when no IMAP host is configured.
    """
    imap = await _get_imap_connection()

    # Mock data fallback when IMAP is not configured
    if imap is None:
        return [
            {"id": "msg_1", "subject": "School update: upcoming holidays", "from": "school@edu.nl", "preview": "Dear parents, please note that summer holidays start next week.", "unread": True},
            {"id": "msg_2", "subject": "Radiale CalDAV Server Update", "from": "admin@local.lan", "preview": "The local radicale container has updated successfully.", "unread": False},
            {"id": "msg_3", "subject": "Factuur July 2026", "from": "billing@energy.nl", "preview": "Your monthly energy invoice is ready for download.", "unread": True},
            {"id": "msg_4", "subject": "Spam Offer: Cheap vacations", "from": "spam@deals.com", "preview": "Click here to win a free trip to Hawaii!", "unread": True}
        ]

    try:
        await imap.select("INBOX")

        # Search criteria: UNSEEN for unread_only, otherwise UNKEYWORD NovaProcessed
        # (IMAP drops the $ prefix in KEYWORD/UNKEYWORD)
        if unread_only:
            criteria = "UNSEEN"
        else:
            criteria = "UNKEYWORD NovaProcessed"

        result, uid_data = await imap.uid("search", None, criteria)
        # uid_data is [b'1 2 3'] — decode and split
        uids = []
        if uid_data and uid_data[0]:
            uid_str = uid_data[0].decode("utf-8", errors="replace") if isinstance(uid_data[0], bytes) else uid_data[0]
            uids = uid_str.split()

        emails = []
        for uid_b in uids[-limit:]:
            uid = uid_b.decode("utf-8", errors="replace") if isinstance(uid_b, bytes) else uid_b
            result, msg_data = await imap.uid(
                "fetch", uid,
                "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)] FLAGS)"
            )

            subject = _parse_header(msg_data, "Subject")
            from_addr = _parse_header(msg_data, "From")
            flags = _parse_flags(msg_data)

            emails.append({
                "id": str(uid),
                "subject": subject or "No Subject",
                "from": from_addr or "Unknown",
                "preview": "",
                "unread": "\\Seen" not in flags,
            })

        return emails

    finally:
        try:
            await imap.logout()
        except Exception:
            pass


async def _mark_email_processed(uid: str) -> None:
    """Mark an email as processed via IMAP flags.

    Sets \\Seen + $NovaProcessed. Falls back to \\Seen + \\Flagged
    if the server rejects the custom flag (per Pitfall 3).
    No-op if IMAP host is not configured.
    """
    imap = await _get_imap_connection()
    if imap is None:
        return

    try:
        result, _ = await imap.uid("store", uid, "+FLAGS", "(\\Seen $NovaProcessed)")
        if result == "NO":
            # Custom flag rejected — fall back to \\Flagged
            await imap.uid("store", uid, "+FLAGS", "(\\Seen \\Flagged)")
    finally:
        try:
            await imap.logout()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Business logic (unchanged per D-10, D-11, D-12)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# SMTP sender (new per D-03, D-04)
# ---------------------------------------------------------------------------

async def send_email_message(to: str, subject: str, body: str) -> dict:
    """Send an email via SMTP relay. Returns status dict with {success, code, message}."""
    message = EmailMessage()
    message["From"] = f"nova@{settings.nova_domain}" if settings.nova_domain else ""
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    response = await aiosmtplib.send(
        message,
        hostname=settings.nova_smtp_host,
        port=settings.nova_smtp_port,
        username=settings.nova_smtp_user,
        password=settings.nova_smtp_pass,
        use_tls=settings.nova_smtp_use_tls,
    )
    return {"success": 200 <= response.code < 300, "code": response.code, "message": response.message}


# ---------------------------------------------------------------------------
# Tools (registered in TOOLS dict via @tool decorator)
# ---------------------------------------------------------------------------

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
    emails = await fetch_emails_imap(limit=10)
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
    description="List recent emails from the shared mailbox, newest first.",
    parameters={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "How many to fetch (default 10)."},
            "unread_only": {"type": "boolean", "description": "Only unread messages."},
        },
    },
)
async def list_recent_emails(limit: int = 10, unread_only: bool = False) -> str:
    emails = await fetch_emails_imap(limit=limit, unread_only=unread_only)
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


@tool(
    name="send_email",
    description="Send an email via SMTP. Returns confirmation or error.",
    parameters={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient email address."},
            "subject": {"type": "string", "description": "Email subject line."},
            "body": {"type": "string", "description": "Email body text."},
        },
        "required": ["to", "subject", "body"],
    },
)
async def send_email(to: str, subject: str, body: str) -> str:
    """Send an email via SMTP and return a confirmation message."""
    result = await send_email_message(to, subject, body)
    if result["success"]:
        return f"Email sent to {to} (subject: {subject})."
    return f"Failed to send email: SMTP {result['code']}."
