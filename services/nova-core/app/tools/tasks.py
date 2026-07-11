"""Tasks/todos tool — STUB.

Phase 5 replaces these bodies with real Postgres queries against the `tasks` table
(see infra/postgres/init/01_schema.sql). Signatures & specs are stable so the agent
loop and dashboard endpoints can be built against them now.
"""
from __future__ import annotations

from .base import tool


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
    # TODO(Phase 5): INSERT INTO tasks (...) VALUES (...)
    due = f" (due {due_at})" if due_at else ""
    return f"[stub] Added task '{title}' for {assignee}{due}."


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
    # TODO(Phase 5): SELECT ... FROM tasks WHERE status='active' [AND assignee=...]
    who = f" for {assignee}" if assignee else ""
    return f"[stub] No active tasks{who} yet."


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
    # TODO(Phase 5): UPDATE tasks SET status='done', completed_at=now() WHERE ...
    return f"[stub] Marked '{title}' done."
