"""Tasks/todos tool using PostgreSQL."""
from __future__ import annotations

from datetime import datetime

from .base import tool
from ..db import get_pool


async def _get_user_uuid(conn, name: str) -> str | None:
    row = await conn.fetchrow("SELECT id FROM users WHERE name = $1", name)
    if row:
        return str(row["id"])
    # Fallback to household if not found
    row = await conn.fetchrow("SELECT id FROM users WHERE name = 'household'")
    if row:
        return str(row["id"])
    return None


@tool(
    name="add_task",
    description="Add a task/todo to the shared household list, optionally with a deadline and assignee.",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "What needs doing."},
            "assignee": {
                "type": "string",
                "enum": ["Ruben", "Meral", "household"],
                "description": "Who the task is for. Defaults to the requester.",
            },
            "due_at": {
                "type": "string",
                "description": "ISO 8601 deadline, e.g. 2026-07-15T16:00:00. Omit if none.",
            },
        },
        "required": ["title"],
    },
)
async def add_task(title: str, user: str, assignee: str | None = None, due_at: str | None = None) -> str:
    assignee = assignee or user
    pool = await get_pool()
    async with pool.acquire() as conn:
        assignee_uuid = await _get_user_uuid(conn, assignee)
        creator_uuid = await _get_user_uuid(conn, user)
        
        due_dt = None
        if due_at:
            try:
                # Remove Z/tz offset suffix if any or parse directly
                due_dt = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
            except ValueError:
                return f"Error: Invalid date format for due_at: '{due_at}'"

        await conn.execute(
            """
            INSERT INTO tasks (title, assignee_id, created_by, due_at)
            VALUES ($1, $2, $3, $4)
            """,
            title,
            assignee_uuid,
            creator_uuid,
            due_dt
        )
        
    due = f" (due {due_at})" if due_at else ""
    return f"Added task '{title}' for {assignee}{due}."


@tool(
    name="list_tasks",
    description="List active household tasks, optionally filtered by assignee.",
    parameters={
        "type": "object",
        "properties": {
            "assignee": {
                "type": "string",
                "enum": ["Ruben", "Meral", "household"],
            },
        },
    },
)
async def list_tasks(assignee: str | None = None) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if assignee:
            assignee_uuid = await _get_user_uuid(conn, assignee)
            rows = await conn.fetch(
                """
                SELECT t.title, t.due_at
                FROM tasks t
                WHERE t.status = 'active' AND t.assignee_id = $1
                ORDER BY t.due_at ASC NULLS LAST, t.created_at ASC
                """,
                assignee_uuid
            )
        else:
            rows = await conn.fetch(
                """
                SELECT t.title, u.name as assignee, t.due_at
                FROM tasks t
                LEFT JOIN users u ON t.assignee_id = u.id
                WHERE t.status = 'active'
                ORDER BY t.due_at ASC NULLS LAST, t.created_at ASC
                """
            )
            
    if not rows:
        who = f" for {assignee}" if assignee else ""
        return f"No active tasks{who} yet."
        
    lines = []
    for i, row in enumerate(rows, 1):
        due_str = ""
        if row["due_at"]:
            due_str = f" (due {row['due_at'].isoformat()})"
        
        if assignee:
            lines.append(f"{i}. {row['title']}{due_str}")
        else:
            assignee_name = row["assignee"] or "unassigned"
            lines.append(f"{i}. {row['title']} [assigned to {assignee_name}]{due_str}")
            
    who = f" for {assignee}" if assignee else " (all)"
    return f"Active tasks{who}:\n" + "\n".join(lines)


@tool(
    name="complete_task",
    description="Mark a household task as done.",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Title (or close match) of the task to complete."},
        },
        "required": ["title"],
    },
)
async def complete_task(title: str) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Try exact match first
        res = await conn.execute(
            "UPDATE tasks SET status = 'done', completed_at = now() WHERE title = $1 AND status = 'active'",
            title
        )
        # If not exact match, try ILIKE substring
        if res == "UPDATE 0":
            res = await conn.execute(
                "UPDATE tasks SET status = 'done', completed_at = now() WHERE title ILIKE $1 AND status = 'active'",
                f"%{title}%"
            )
            
    if res != "UPDATE 0":
        return f"Marked '{title}' done."
    return f"Could not find active task matching '{title}'."
