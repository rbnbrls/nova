"""Email tool (shared Outlook mailbox via Microsoft Graph) — STUB.

Phase 5 wires this to Microsoft Graph (Mail.Read on the shared mailbox). The local
LLM classifies "important" and summarizes; this tool only fetches.
"""
from __future__ import annotations

from .base import tool


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
    # TODO(Phase 5): GET /users/{mailbox}/messages via Microsoft Graph.
    scope = "unread " if unread_only else ""
    return f"[stub] No {scope}emails to show (last {limit})."
