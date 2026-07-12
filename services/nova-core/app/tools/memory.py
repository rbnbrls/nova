"""Memory tools: remember, forget, list_memories with privacy scope support."""
from __future__ import annotations

from .base import tool
from ..db import get_pool
from .tasks import _get_user_uuid


@tool(
    name="remember",
    description="Save something Nova should remember about the current user or the household. "
                 "Use this when the user shares a preference, fact, or piece of information "
                 "they want recalled later.",
    parameters={
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The fact or piece of information to remember.",
            },
            "scope": {
                "type": "string",
                "enum": ["private", "household"],
                "description": "'private' — only visible to the user who saved it. "
                               "'household' — visible to all household members. Defaults to private.",
            },
        },
        "required": ["content"],
    },
)
async def remember(content: str, user: str, scope: str = "private") -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        user_id = await _get_user_uuid(conn, user)
        if not user_id:
            return "Error: User not found."
        await conn.execute(
            "INSERT INTO memories (user_id, content, scope) VALUES ($1, $2, $3)",
            user_id,
            content,
            scope,
        )
    short = content[:80] + "..." if len(content) > 80 else content
    return f"Remembered: {short}"


@tool(
    name="forget",
    description="Forget a previously saved memory. Only forgets memories owned by the requesting user. "
                 "Optionally filter by scope.",
    parameters={
        "type": "object",
        "properties": {
            "content_pattern": {
                "type": "string",
                "description": "Substring to match against memory content (case-insensitive).",
            },
            "scope": {
                "type": "string",
                "enum": ["private", "household"],
                "description": "Optional scope filter. Omit to forget from both scopes.",
            },
        },
        "required": ["content_pattern"],
    },
)
async def forget(content_pattern: str, user: str, scope: str | None = None) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        user_id = await _get_user_uuid(conn, user)
        if not user_id:
            return "Error: User not found."
        if scope:
            result = await conn.execute(
                "DELETE FROM memories WHERE user_id = $1 AND content ILIKE $2 AND scope = $3",
                user_id,
                f"%{content_pattern}%",
                scope,
            )
        else:
            result = await conn.execute(
                "DELETE FROM memories WHERE user_id = $1 AND content ILIKE $2",
                user_id,
                f"%{content_pattern}%",
            )
    count = int(result.split()[-1])
    if count == 0:
        return "No matching memories found to forget."
    word = "memory" if count == 1 else "memories"
    return f"Forgot {count} matching {word}."


@tool(
    name="list_memories",
    description="List your saved memories, optionally filtered by scope.",
    parameters={
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "enum": ["private", "household"],
                "description": "Optional scope filter. Omit to list all of your memories.",
            },
        },
    },
)
async def list_memories(user: str, scope: str | None = None) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        user_id = await _get_user_uuid(conn, user)
        if not user_id:
            return "Error: User not found."
        if scope:
            rows = await conn.fetch(
                "SELECT content, scope, created_at FROM memories "
                "WHERE user_id = $1 AND scope = $2 "
                "ORDER BY created_at DESC",
                user_id,
                scope,
            )
        else:
            rows = await conn.fetch(
                "SELECT content, scope, created_at FROM memories "
                "WHERE user_id = $1 "
                "ORDER BY created_at DESC",
                user_id,
            )
    if not rows:
        return "No saved memories."
    lines = [
        f"- {r['content']} [{r['scope']}] (saved {r['created_at'].strftime('%Y-%m-%d')})"
        for r in rows
    ]
    return f"You have {len(rows)} saved memories:\n" + "\n".join(lines)
