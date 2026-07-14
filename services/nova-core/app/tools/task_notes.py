"""Task notes tool — add, list, and delete notes on tasks."""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone

from .base import tool
from ..db import get_pool

_TOOL_TAG = "task_notes"


@tool(
    name="add_task_note",
    description="Add a note to an existing household task.",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "UUID of the task to add a note to.",
            },
            "content": {
                "type": "string",
                "description": "The note text.",
            },
        },
        "required": ["task_id", "content"],
    },
)
async def add_task_note(task_id: str, content: str, user: str) -> str:
    try:
        _uuid.UUID(task_id)
    except ValueError:
        return f"Error: Invalid task_id UUID: '{task_id}'."

    if not content or not content.strip():
        return "Error: Note content cannot be empty."

    pool = await get_pool()
    async with pool.acquire() as conn:
        task = await conn.fetchval(
            "SELECT id FROM tasks WHERE id = $1::uuid AND status = 'active'",
            task_id,
        )
        if not task:
            return f"Error: No active task found with id '{task_id}'."

        author_uuid = None
        if user:
            row = await conn.fetchrow("SELECT id FROM users WHERE name = $1", user)
            if row:
                author_uuid = row["id"]

        note_id = await conn.fetchval(
            """
            INSERT INTO task_notes (task_id, content, author_id)
            VALUES ($1::uuid, $2, $3::uuid)
            RETURNING id
            """,
            task_id,
            content.strip(),
            author_uuid,
        )

    return f"Note added to task {task_id} (note id: {str(note_id)})."


@tool(
    name="list_task_notes",
    description="List all notes for a given task, newest first.",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "UUID of the task whose notes to list.",
            },
        },
        "required": ["task_id"],
    },
)
async def list_task_notes(task_id: str) -> str:
    try:
        _uuid.UUID(task_id)
    except ValueError:
        return f"Error: Invalid task_id UUID: '{task_id}'."

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT tn.id, tn.content, tn.created_at, u.name as author
            FROM task_notes tn
            LEFT JOIN users u ON tn.author_id = u.id
            WHERE tn.task_id = $1::uuid
            ORDER BY tn.created_at DESC
            """,
            task_id,
        )

    if not rows:
        return f"No notes for task {task_id}."

    lines = []
    for i, row in enumerate(rows, 1):
        author = row["author"] or "unknown"
        ts = row["created_at"].isoformat() if row["created_at"] else ""
        lines.append(f"{i}. [{ts}] {author}: {row['content']}")

    return f"Notes for task {task_id}:\n" + "\n".join(lines)


@tool(
    name="delete_task_note",
    description="Delete a note by its UUID.",
    parameters={
        "type": "object",
        "properties": {
            "note_id": {
                "type": "string",
                "description": "UUID of the note to delete.",
            },
        },
        "required": ["note_id"],
    },
)
async def delete_task_note(note_id: str) -> str:
    try:
        _uuid.UUID(note_id)
    except ValueError:
        return f"Error: Invalid note_id UUID: '{note_id}'."

    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM task_notes WHERE id = $1::uuid",
            note_id,
        )
        if result == "DELETE 0":
            return f"Error: No note found with id '{note_id}'."

    return f"Note {note_id} deleted."
