"""Recurring chore tools with rotation tracking and fair-share nudges.

Chores are stored in the `tasks` table with `is_chore=true` to distinguish
them from regular tasks. Recurring chores auto-rotate assignee between
household members on completion. Fair-share computation surfaces when one
person has done a chore disproportionately more times.
"""
from __future__ import annotations

from datetime import datetime

from .base import tool
from ..db import get_pool
from .tasks import _get_user_uuid


@tool(
    name="add_chore",
    description="Add a recurring household chore with optional rotation. "
                "Chores appear alongside tasks but have recurrence and rotation support.",
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "The chore name, e.g. 'Dishes' or 'Vacuum living room'.",
            },
            "assignee": {
                "type": "string",
                "enum": ["Ruben", "Meral", "household"],
                "description": "Who the chore is initially assigned to. Defaults to the requester.",
            },
            "recurrence_pattern": {
                "type": "string",
                "description": "How often the chore repeats, e.g. 'weekly', 'biweekly', 'monthly'.",
            },
            "rotation_group": {
                "type": "string",
                "description": "Optional group name for rotation scoping, e.g. 'kitchen', 'bathroom'.",
            },
            "due_at": {
                "type": "string",
                "description": "ISO 8601 deadline, e.g. 2026-07-15T16:00:00. Omit if none.",
            },
        },
        "required": ["title", "recurrence_pattern"],
    },
)
async def add_chore(
    title: str,
    recurrence_pattern: str,
    user: str,
    assignee: str | None = None,
    rotation_group: str | None = None,
    due_at: str | None = None,
) -> str:
    # Validate recurrence_pattern is not empty
    if not recurrence_pattern or not recurrence_pattern.strip():
        return "Error: recurrence_pattern is required for chores."

    assignee = assignee or user
    pool = await get_pool()
    async with pool.acquire() as conn:
        assignee_uuid = await _get_user_uuid(conn, assignee)
        creator_uuid = await _get_user_uuid(conn, user)

        due_dt = None
        if due_at:
            try:
                due_dt = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
            except ValueError:
                return f"Error: Invalid date format for due_at: '{due_at}'"

        await conn.execute(
            """
            INSERT INTO tasks (title, assignee_id, created_by, due_at, is_chore,
                               recurrence_pattern, rotation_group, last_rotation_assignee_id)
            VALUES ($1, $2, $3, $4, true, $5, $6, NULL)
            """,
            title,
            assignee_uuid,
            creator_uuid,
            due_dt,
            recurrence_pattern.strip(),
            rotation_group,
        )

    result = f"Added chore '{title}' for {assignee} (recurring: {recurrence_pattern.strip()})"
    if rotation_group:
        result += f" [{rotation_group}]"
    result += "."
    return result


@tool(
    name="list_chores",
    description="List all active recurring chores with rotation and fair-share information.",
    parameters={
        "type": "object",
        "properties": {
            "rotation_group": {
                "type": "string",
                "description": "Optional group name to filter by, e.g. 'kitchen'.",
            },
        },
    },
)
async def list_chores(rotation_group: str | None = None) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        conditions = ["t.status = 'active'", "t.is_chore = true"]
        params = []

        if rotation_group:
            conditions.append(f"t.rotation_group = ${len(params) + 1}")
            params.append(rotation_group)

        where = " AND ".join(conditions)

        rows = await conn.fetch(
            f"""
            SELECT t.id, t.title, t.recurrence_pattern, t.rotation_group,
                   u.name AS assignee_name,
                   lr.name AS last_assignee_name
            FROM tasks t
            LEFT JOIN users u ON t.assignee_id = u.id
            LEFT JOIN users lr ON t.last_rotation_assignee_id = lr.id
            WHERE {where}
            ORDER BY t.created_at ASC
            """,
            *params,
        )

    if not rows:
        return "No recurring chores configured."

    lines = []
    for i, row in enumerate(rows, 1):
        parts = [row["title"]]
        assignee = row["assignee_name"] or "unassigned"
        parts.append(f"— assigned to {assignee}")
        parts.append(f"[{row['recurrence_pattern']}]")
        if row["rotation_group"]:
            parts.append(f"[{row['rotation_group']}]")
        lines.append(f"{i}. {' '.join(parts)}")

        # Compute fair-share nudge for chores with a rotation_group
        if row["rotation_group"]:
            # Check completions in the last 30 days for this rotation_group
            chore_lines = await _compute_fairness_nudge(conn, row["rotation_group"])
            if chore_lines:
                lines.extend(chore_lines)

    return "Recurring chores:\n" + "\n".join(lines)


async def _compute_fairness_nudge(conn, rotation_group: str) -> list[str]:
    """Return fair-share nudge lines for a given rotation_group, or empty list if balanced."""
    rows = await conn.fetch(
        """
        SELECT u.name AS name, COUNT(*) AS count
        FROM chore_rotation_log crl
        JOIN users u ON crl.completed_by = u.id
        WHERE crl.rotation_group = $1
          AND crl.completed_at >= now() - INTERVAL '30 days'
        GROUP BY u.name
        ORDER BY count DESC
        """,
        rotation_group,
    )
    if not rows:
        return []

    # Build name->count mapping
    counts = {r["name"]: r["count"] for r in rows}
    names = list(counts.keys())

    # Check if any user is ahead by 2+ completions
    if len(names) >= 2:
        max_count = max(counts.values())
        min_count = min(counts.values())
        if max_count - min_count >= 2:
            details = ", ".join(f"{name} has done this {count}x" for name, count in rows)
            return [f"   ⚖️ Fair-share: {details} this month."]

    return []


@tool(
    name="complete_chore",
    description="Mark a chore as done. If the chore has a recurrence pattern, a new instance "
                "is created with the next assignee in rotation.",
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Title (or close match) of the chore to complete.",
            },
        },
        "required": ["title"],
    },
)
async def complete_chore(title: str, user: str) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Find the chore — try exact match first
        row = await conn.fetchrow(
            """
            SELECT id, title, recurrence_pattern, rotation_group,
                   assignee_id, last_rotation_assignee_id
            FROM tasks
            WHERE title = $1 AND is_chore = true AND status = 'active'
            """,
            title,
        )

        # Fallback to ILIKE substring match
        if not row:
            row = await conn.fetchrow(
                """
                SELECT id, title, recurrence_pattern, rotation_group,
                       assignee_id, last_rotation_assignee_id
                FROM tasks
                WHERE title ILIKE $1 AND is_chore = true AND status = 'active'
                """,
                f"%{title}%",
            )

        if not row:
            return f"Could not find active chore matching '{title}'."

        chore_id = row["id"]
        recurrence_pattern = row["recurrence_pattern"]
        rotation_group = row["rotation_group"]

        # Mark current chore as done
        completed_by_uuid = await _get_user_uuid(conn, user)
        await conn.execute(
            """
            UPDATE tasks SET status = 'done', completed_at = now()
            WHERE id = $1
            """,
            chore_id,
        )

        # If recurring, create next instance with rotation
        if recurrence_pattern:
            # Log rotation
            await conn.execute(
                """
                INSERT INTO chore_rotation_log (chore_id, completed_by, rotation_group)
                VALUES ($1, $2, $3)
                """,
                chore_id,
                completed_by_uuid,
                rotation_group,
            )

            # Determine next assignee
            next_assignee_name = await _determine_next_assignee(
                conn, rotation_group, row, user, completed_by_uuid,
            )

            next_assignee_uuid = await _get_user_uuid(conn, next_assignee_name)

            # Insert the next chore instance
            await conn.execute(
                """
                INSERT INTO tasks (title, assignee_id, created_by, is_chore,
                                   recurrence_pattern, rotation_group,
                                   last_rotation_assignee_id)
                VALUES ($1, $2, $3, true, $4, $5, $6)
                """,
                row["title"],
                next_assignee_uuid,
                completed_by_uuid,
                recurrence_pattern,
                rotation_group,
                completed_by_uuid,
            )

            # Compute fairness nudge
            fairness = ""
            if rotation_group:
                nudge_lines = await _compute_fairness_nudge(conn, rotation_group)
                if nudge_lines:
                    fairness = " " + nudge_lines[0].strip()

            return (
                f"Completed chore '{row['title']}'. "
                f"Next instance assigned to {next_assignee_name}.{fairness}"
            )
        else:
            return f"Completed chore '{row['title']}'."


async def _determine_next_assignee(
    conn, rotation_group: str | None, chore_row: dict, user: str, completed_by_uuid: str | None,
) -> str:
    """Determine the next assignee for a recurring chore.

    If rotation_group is set, alternate between Ruben and Meral.
    If no rotation_group, keep the same assignee.
    """
    if not rotation_group:
        # No rotation group — keep current assignee
        assignee_id = chore_row["assignee_id"]
        row = await conn.fetchrow("SELECT name FROM users WHERE id = $1", assignee_id)
        return row["name"] if row else user

    # Determine the two household members
    members = await conn.fetch(
        "SELECT id, name FROM users WHERE name IN ('Ruben', 'Meral') ORDER BY name",
    )
    member_ids = {str(r["id"]): r["name"] for r in members}

    if len(member_ids) < 2:
        # Fallback: no rotation possible
        return user

    # Get the last assignee who did this chore
    last_assignee_id = chore_row["last_rotation_assignee_id"]
    last_assignee_str = str(last_assignee_id) if last_assignee_id else None

    if last_assignee_str and last_assignee_str in member_ids:
        # Flip to the other member
        for mid, mname in member_ids.items():
            if mid != last_assignee_str:
                return mname
    else:
        # First completion — flip from original assignee
        original_assignee_id = str(chore_row["assignee_id"]) if chore_row["assignee_id"] else None
        if original_assignee_id and original_assignee_id in member_ids:
            for mid, mname in member_ids.items():
                if mid != original_assignee_id:
                    return mname

    return user
