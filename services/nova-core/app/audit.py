"""Audit trail module — record mutating tool calls to the audit_log table.

Every add_task, complete_task, and create_event invocation (confirmed or denied)
is recorded here with a timestamp, user, tool name, action summary, and status.
"""
from __future__ import annotations

import logging

from . import db

log = logging.getLogger("nova-core.audit")


async def record_tool_call(
    user_name: str,
    tool_name: str,
    action_summary: str,
    status: str = "completed",
    confirmation_required: bool = False,
) -> int | None:
    """Insert a row into audit_log and return the new row id.

    Returns None if the database write fails (the caller should not crash).
    """
    pool = await db.get_pool()
    try:
        async with pool.acquire() as conn:
            row_id = await conn.fetchval(
                """
                INSERT INTO audit_log (user_name, tool_name, action_summary, status, confirmation_required)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                user_name,
                tool_name,
                action_summary,
                status,
                confirmation_required,
            )
        return row_id
    except Exception:
        log.exception("Failed to record audit_log entry")
        return None
