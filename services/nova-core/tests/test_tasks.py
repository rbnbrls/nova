"""Tests for the tasks tool (PostgreSQL-backed).

Covers TASK-01 through TASK-04: task creation, deadline parsing,
listing/filtering, and completion.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.tools.tasks import add_task, list_tasks, complete_task, rename_task, reassign_task, get_task_detail, create_from_template

_TASK1_ID = "00000000-0000-0000-0000-000000000001"
_TASK2_ID = "00000000-0000-0000-0000-000000000002"


def _make_mock_pool(mock_conn: AsyncMock) -> MagicMock:
    """Build an asyncpg pool mock that yields *mock_conn* via acquire()."""
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = mock_conn
    return pool


async def _fetchrow_side_effect(query: str, *params: str) -> dict | None:
    """Simulate asyncpg fetchrow for the user-lookup queries used by tasks."""
    if params:
        name = params[0]
        if name in ("Ruben", "Meral", "household"):
            return {"id": f"uuid-{name.lower()}"}
        return None
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
    conn.fetchval.return_value = _uuid.UUID(_TASK1_ID)

    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await add_task("buy milk", user="Ruben")
        assert result == "Added task 'buy milk' for Ruben."
        assert conn.fetchval.called
        insert_sql = conn.fetchval.call_args[0][0]
        assert "INSERT INTO tasks" in insert_sql

        conn.reset_mock()
        conn.fetchrow.side_effect = _fetchrow_side_effect
        conn.fetchval.return_value = _uuid.UUID(_TASK2_ID)

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
    conn.fetchval.return_value = _uuid.UUID(_TASK1_ID)

    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await add_task("file taxes", user="Ruben", due_at="2026-07-15T16:00:00+02:00")
        assert result == "Added task 'file taxes' for Ruben (due 2026-07-15T16:00:00+02:00)."

        conn.reset_mock()
        conn.fetchrow.side_effect = _fetchrow_side_effect
        conn.fetchval.return_value = _uuid.UUID(_TASK2_ID)

        result = await add_task("meeting", user="Ruben", due_at="2026-07-20T10:00:00Z")
        assert result == "Added task 'meeting' for Ruben (due 2026-07-20T10:00:00Z)."


@pytest.mark.asyncio
async def test_add_task_rejects_invalid_due_date():
    """TASK-02: A non-parseable due-date string returns an error."""
    conn = AsyncMock()
    conn.fetchrow.side_effect = _fetchrow_side_effect
    conn.fetchval.return_value = _uuid.UUID(_TASK1_ID)

    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await add_task("bad date", user="Ruben", due_at="next Thursday at 4pm")
        assert "Error: Invalid date format" in result
        # fetchval should not have been called (INSERT not reached)
        assert conn.fetchval.call_count == 0


# ---------------------------------------------------------------------------
# TASK-03 : List / filter tasks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_tasks_filter_by_assignee():
    """TASK-03: Listing tasks scoped to a single assignee returns only theirs."""
    conn = AsyncMock()
    conn.fetchrow.side_effect = _fetchrow_side_effect

    def _fetch_side_effect(query: str, *params) -> list[dict]:
        if "td.child_id" in query or "FROM task_dependencies" in query:
            return []
        if params and params[0] == "uuid-ruben":
            return [
                {"id": _TASK1_ID, "title": "buy milk", "due_at": datetime(2026, 7, 15, 16, 0, 0)},
            ]
        return [
            {"id": _TASK1_ID, "title": "buy milk", "assignee": "Ruben", "due_at": datetime(2026, 7, 15, 16, 0, 0)},
            {"id": _TASK2_ID, "title": "pay bills", "assignee": "Meral", "due_at": None},
        ]
    conn.fetch.side_effect = _fetch_side_effect

    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await list_tasks(assignee="Ruben")
        assert "Active tasks for Ruben" in result
        assert "buy milk" in result

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
    conn.fetchval.return_value = _uuid.UUID(_TASK1_ID)
    conn.fetch.return_value = []

    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await complete_task("buy milk")
        assert result == "Marked 'buy milk' done."
        # First fetchval is the exact-match UPDATE query
        exact_sql = conn.fetchval.call_args_list[0][0][0]
        assert "title = $1" in exact_sql


@pytest.mark.asyncio
async def test_complete_task_ilike_fallback():
    """TASK-04: When exact match fails, ILIKE substring fallback is tried."""
    conn = AsyncMock()
    # Phase 44 adds a third fetchval call for assignee lookup in the replan hook
    conn.fetchval.side_effect = [None, _uuid.UUID(_TASK1_ID), "Ruben"]
    conn.fetch.return_value = []

    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await complete_task("milk")
        assert result == "Marked 'milk' done."
        call_sqls = [c[0][0] for c in conn.fetchval.call_args_list]
        # First two sql calls are the UPDATE queries (exact then ILIKE)
        assert "title = $1" in call_sqls[0], f"Got: {call_sqls[0][:80]}"
        assert "title ILIKE" in call_sqls[1], f"Got: {call_sqls[1][:80]}"


@pytest.mark.asyncio
async def test_complete_task_not_found():
    """TASK-04: A task that can't be found returns a clear error message."""
    conn = AsyncMock()
    conn.fetchval.return_value = None

    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await complete_task("nonexistent")
        assert "Could not find" in result


# ---------------------------------------------------------------------------
# Priority field (Phase 4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_task_default_priority():
    """add_task defaults to medium priority when none specified."""
    conn = AsyncMock()
    conn.fetchrow.side_effect = _fetchrow_side_effect
    conn.fetchval.return_value = _uuid.UUID(_TASK1_ID)

    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await add_task("test", user="Ruben")
        assert "Added task" in result
        call_args = conn.fetchval.call_args
        sql = call_args[0][0]
        vals = call_args[0][1:]
        assert '"priority"' in sql or "priority" in sql
        assert vals[4] == "medium"  # priority is param $5


@pytest.mark.asyncio
async def test_add_task_explicit_priority():
    """add_task accepts and stores explicit priority values."""
    conn = AsyncMock()
    conn.fetchrow.side_effect = _fetchrow_side_effect
    conn.fetchval.return_value = _uuid.UUID(_TASK1_ID)

    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await add_task("urgent task", user="Ruben", priority="high")
        assert "[high]" in result
        call_args = conn.fetchval.call_args
        vals = call_args[0][1:]
        assert vals[4] == "high"  # priority is param $5


@pytest.mark.asyncio
async def test_list_tasks_label_filter():
    """list_tasks accepts a labels filter using array overlap."""
    conn = AsyncMock()
    conn.fetchrow.side_effect = _fetchrow_side_effect

    def _fetch_side_effect(query: str, *params):
        if "td.child_id" in query or "FROM task_dependencies" in query:
            return []
        return [
            {"id": _TASK1_ID, "title": "buy groceries", "due_at": datetime(2026, 7, 15, 16, 0, 0), "priority": "medium", "assignee": "Ruben", "labels": ["groceries", "weekly"], "is_template": False},
        ]
    conn.fetch.side_effect = _fetch_side_effect

    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await list_tasks(labels="groceries")
        assert "buy groceries" in result


# ---------------------------------------------------------------------------
# Phase 45: rename_task
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rename_task_success():
    conn = AsyncMock()
    conn.execute.return_value = "UPDATE 1"
    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await rename_task(_TASK1_ID, "Buy organic milk")
        assert "renamed to" in result


@pytest.mark.asyncio
async def test_rename_task_not_found():
    conn = AsyncMock()
    conn.execute.return_value = "UPDATE 0"
    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await rename_task(_TASK1_ID, "New name")
        assert "No active task" in result


@pytest.mark.asyncio
async def test_rename_task_empty_title():
    result = await rename_task(_TASK1_ID, "")
    assert "cannot be empty" in result


# ---------------------------------------------------------------------------
# Phase 45: reassign_task
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reassign_task_success():
    conn = AsyncMock()
    conn.fetchrow.side_effect = _fetchrow_side_effect
    conn.execute.return_value = "UPDATE 1"
    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await reassign_task(_TASK1_ID, "Meral", user="Ruben")
        assert "reassigned to Meral" in result


@pytest.mark.asyncio
async def test_reassign_task_not_found():
    conn = AsyncMock()
    conn.fetchrow.side_effect = _fetchrow_side_effect
    conn.execute.return_value = "UPDATE 0"
    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await reassign_task(_TASK1_ID, "Meral", user="Ruben")
        assert "No active task" in result


# ---------------------------------------------------------------------------
# Phase 45: get_task_detail
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_task_detail_success():
    conn = AsyncMock()
    conn.fetchrow.return_value = {
        "id": _TASK1_ID,
        "title": "buy milk",
        "due_at": datetime(2026, 7, 15, 16, 0, 0),
        "priority": "high",
        "status": "active",
        "assignee": "Ruben",
        "created_by": "Ruben",
        "planning_state": "in_progress",
        "labels": ["groceries"],
        "is_template": False,
        "template_id": None,
        "task_duration_min": 30,
        "earliest_start": None,
        "latest_end": None,
        "hard_deadline": None,
        "soft_deadline": None,
        "created_at": datetime(2026, 7, 14),
    }
    conn.fetch.side_effect = [
        [],  # blockers
        [],  # dependents
    ]
    conn.fetchval.return_value = 2  # note count
    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await get_task_detail(_TASK1_ID)
        assert "Title: buy milk" in result
        assert "Assignee: Ruben" in result
        assert "Priority: high" in result
        assert "Planning state: in_progress" in result
        assert "Notes: 2" in result


@pytest.mark.asyncio
async def test_get_task_detail_not_found():
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await get_task_detail(_TASK1_ID)
        assert "No task found" in result


# ---------------------------------------------------------------------------
# Phase 45: create_from_template
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_from_template_success():
    conn = AsyncMock()
    conn.fetchrow.side_effect = [
        {"title": "Weekly Clean", "labels": ["chores"], "priority": "low", "task_duration_min": 60},
        {"id": "uuid-ruben"},
        {"id": "uuid-ruben"},
    ]
    conn.fetchval.return_value = _uuid.UUID(_TASK1_ID)
    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await create_from_template(_TASK1_ID, user="Ruben")
        assert "Created task" in result
        assert "from template" in result


@pytest.mark.asyncio
async def test_create_from_template_not_found():
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await create_from_template(_TASK1_ID, user="Ruben")
        assert "No active template" in result


@pytest.mark.asyncio
async def test_list_tasks_due_before_filter():
    """list_tasks accepts a due_before filter that restricts results."""
    conn = AsyncMock()
    conn.fetchrow.side_effect = _fetchrow_side_effect

    def _fetch_side_effect(query: str, *params):
        if "td.child_id" in query or "FROM task_dependencies" in query:
            return []
        return [
            {"id": _TASK1_ID, "title": "old task", "due_at": datetime(2026, 6, 1), "priority": "low", "assignee": "Ruben"},
        ]
    conn.fetch.side_effect = _fetch_side_effect

    pool = _make_mock_pool(conn)

    with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await list_tasks(due_before="2026-07-01T00:00:00")
        assert "old task" in result
        call_sql = conn.fetch.call_args_list[0][0][0]
        assert "due_at <=" in call_sql
