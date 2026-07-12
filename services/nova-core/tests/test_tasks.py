"""Tests for the tasks tool (PostgreSQL-backed).

Covers TASK-01 through TASK-04: task creation, deadline parsing,
listing/filtering, and completion.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.tasks import add_task, list_tasks, complete_task


def _make_mock_pool(mock_conn: AsyncMock) -> MagicMock:
    """Build an asyncpg pool mock that yields *mock_conn* via acquire()."""
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = mock_conn
    return pool


async def _fetchrow_side_effect(query: str, *params: str) -> dict | None:
    """Simulate asyncpg fetchrow for the user-lookup queries used by tasks."""
    # Parameterised query:  SELECT id FROM users WHERE name = $1
    if params:
        name = params[0]
        if name in ("Ruben", "Meral", "household"):
            return {"id": f"uuid-{name.lower()}"}
        return None
    # Literal fallback query:  SELECT id FROM users WHERE name = 'household'
    if "household" in query:
        return {"id": "uuid-household"}
    return None


# ---------------------------------------------------------------------------
# TASK-01 : Default assignee
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_task_default_assignee_is_user():
    """TASK-01: When no assignee is given, the task defaults to the requesting user."""
    conn = AsyncMock()
    conn.fetchrow.side_effect = _fetchrow_side_effect
    conn.execute.return_value = "INSERT 0 1"

    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        # ── caller is Ruben, no assignee → defaults to Ruben ──────────
        result = await add_task("buy milk", user="Ruben")
        assert result == "Added task 'buy milk' for Ruben."
        # Verify the INSERT was issued with Ruben's UUID
        assert conn.execute.called
        insert_sql = conn.execute.call_args[0][0]
        assert "INSERT INTO tasks" in insert_sql

        conn.reset_mock()
        conn.execute.return_value = "INSERT 0 1"

        # ── caller is Ruben, assignee = Meral → uses Meral ────────────
        result = await add_task("pay bills", user="Ruben", assignee="Meral")
        assert result == "Added task 'pay bills' for Meral."


# ---------------------------------------------------------------------------
# TASK-02 : Deadline (ISO 8601 parsing)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_task_with_valid_iso_due_date():
    """TASK-02: An ISO 8601 due date (with explicit offset) is accepted."""
    conn = AsyncMock()
    conn.fetchrow.side_effect = _fetchrow_side_effect
    conn.execute.return_value = "INSERT 0 1"

    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        # ISO 8601 with positive offset
        result = await add_task("file taxes", user="Ruben", due_at="2026-07-15T16:00:00+02:00")
        assert result == "Added task 'file taxes' for Ruben (due 2026-07-15T16:00:00+02:00)."

        conn.reset_mock()
        conn.execute.return_value = "INSERT 0 1"

        # ISO 8601 with Z suffix
        result = await add_task("meeting", user="Ruben", due_at="2026-07-20T10:00:00Z")
        assert result == "Added task 'meeting' for Ruben (due 2026-07-20T10:00:00Z)."


@pytest.mark.asyncio
async def test_add_task_rejects_invalid_due_date():
    """TASK-02: A non-parseable due-date string returns an error."""
    conn = AsyncMock()
    conn.fetchrow.side_effect = _fetchrow_side_effect
    conn.execute.return_value = "INSERT 0 1"

    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await add_task("bad date", user="Ruben", due_at="next Thursday at 4pm")
        assert "Error: Invalid date format" in result
        # INSERT should not have been executed
        assert conn.execute.call_count == 0


# ---------------------------------------------------------------------------
# TASK-03 : List / filter tasks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_tasks_filter_by_assignee():
    """TASK-03: Listing tasks scoped to a single assignee returns only theirs."""
    conn = AsyncMock()
    conn.fetchrow.side_effect = _fetchrow_side_effect

    def _fetch_side_effect(query: str, *params: str) -> list[dict]:
        if params and params[0] == "uuid-ruben":
            return [
                {"title": "buy milk", "due_at": datetime(2026, 7, 15, 16, 0, 0)},
            ]
        # unfiltered path
        return [
            {"title": "buy milk", "assignee": "Ruben", "due_at": datetime(2026, 7, 15, 16, 0, 0)},
            {"title": "pay bills", "assignee": "Meral", "due_at": None},
        ]
    conn.fetch.side_effect = _fetch_side_effect

    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        # Filtered by assignee
        result = await list_tasks(assignee="Ruben")
        assert "Active tasks for Ruben" in result
        assert "buy milk" in result

        # Unfiltered (all)
        result = await list_tasks()
        assert "Active tasks (all)" in result
        assert "buy milk" in result
        assert "pay bills" in result
        assert "assigned to Ruben" in result
        assert "assigned to Meral" in result


@pytest.mark.asyncio
async def test_list_tasks_no_results():
    """TASK-03: When no tasks match, a friendly empty-state message is returned."""
    conn = AsyncMock()
    conn.fetchrow.side_effect = _fetchrow_side_effect
    conn.fetch.return_value = []

    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await list_tasks(assignee="Ruben")
        assert "No active tasks for Ruben yet." in result

        result = await list_tasks()
        assert "No active tasks yet." in result


# ---------------------------------------------------------------------------
# TASK-04 : Complete task
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_task_exact_match():
    """TASK-04: An exact title match marks the task done."""
    conn = AsyncMock()
    conn.execute.return_value = "UPDATE 1"

    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await complete_task("buy milk")
        assert result == "Marked 'buy milk' done."
        # Should have used exact-match SQL
        exact_sql = conn.execute.call_args[0][0]
        assert "title = $1" in exact_sql


@pytest.mark.asyncio
async def test_complete_task_ilike_fallback():
    """TASK-04: When exact match fails, ILIKE substring fallback is tried."""
    conn = AsyncMock()
    conn.execute.side_effect = ["UPDATE 0", "UPDATE 1"]  # exact → fail, ILIKE → success

    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await complete_task("milk")
        assert result == "Marked 'milk' done."
        # Verify first call was exact, second was ILIKE
        call_sqls = [c[0][0] for c in conn.execute.call_args_list]
        assert "title = $1" in call_sqls[0]
        assert "title ILIKE" in call_sqls[1]
        assert conn.execute.call_count == 2


@pytest.mark.asyncio
async def test_complete_task_not_found():
    """TASK-04: A task that can't be found returns a clear error message."""
    conn = AsyncMock()
    conn.execute.return_value = "UPDATE 0"  # both exact and ILIKE fail

    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await complete_task("nonexistent")
        assert "Could not find" in result
