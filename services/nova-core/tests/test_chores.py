"""Tests for the recurring chore tools with rotation and fair-share nudges.

Covers HC-02: chore creation, listing with fair-share computation,
completion with rotation, and error cases.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.chores import add_chore, list_chores, complete_chore


def _make_mock_pool(mock_conn: AsyncMock) -> MagicMock:
    """Build an asyncpg pool mock that yields *mock_conn* via acquire()."""
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = mock_conn
    return pool


def _fetchrow_side_effect(query: str, *params: str) -> dict | None:
    """Simulate asyncpg fetchrow for the user-lookup queries used by chores."""
    if params:
        name = params[0]
        if name in ("Ruben", "Meral", "household"):
            return {"id": f"uuid-{name.lower()}"}
        return None
    if "household" in query:
        return {"id": "uuid-household"}
    return None


# ---------------------------------------------------------------------------
# add_chore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_chore_creates_with_is_chore():
    """INSERT succeeds, returns confirmation, verifies is_chore=true in SQL params."""
    conn = AsyncMock()
    conn.fetchrow.side_effect = _fetchrow_side_effect
    conn.execute.return_value = "INSERT 0 1"

    pool = _make_mock_pool(conn)

    with patch("app.tools.chores.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await add_chore("Dishes", recurrence_pattern="weekly", user="Ruben")
        assert result == "Added chore 'Dishes' for Ruben (recurring: weekly)."

        insert_sql = conn.execute.call_args[0][0]
        assert "INSERT INTO tasks" in insert_sql
        assert "is_chore" in insert_sql
        # is_chore=true is a SQL literal, not a parameter
        assert "true" in insert_sql.lower()


@pytest.mark.asyncio
async def test_add_chore_requires_recurrence_pattern():
    """Empty recurrence_pattern returns error."""
    conn = AsyncMock()
    pool = _make_mock_pool(conn)

    with patch("app.tools.chores.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await add_chore("Dishes", recurrence_pattern="", user="Ruben")
        assert "Error:" in result
        assert "recurrence_pattern" in result
        conn.execute.assert_not_called()

        # Also test whitespace-only
        result = await add_chore("Dishes", recurrence_pattern="   ", user="Ruben")
        assert "Error:" in result


@pytest.mark.asyncio
async def test_add_chore_with_rotation_group():
    """Rotation_group stored correctly."""
    conn = AsyncMock()
    conn.fetchrow.side_effect = _fetchrow_side_effect
    conn.execute.return_value = "INSERT 0 1"

    pool = _make_mock_pool(conn)

    with patch("app.tools.chores.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await add_chore(
            "Dishes", recurrence_pattern="weekly", user="Ruben",
            rotation_group="kitchen",
        )
        assert "[kitchen]" in result
        insert_params = conn.execute.call_args[0][1:]
        assert insert_params[5] == "kitchen"  # rotation_group


# ---------------------------------------------------------------------------
# list_chores
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_chores_shows_active_chores():
    """Returns formatted list with recurrence info."""
    conn = AsyncMock()
    # Use side_effect to handle list_chores query + subsequent fairness queries
    conn.fetch.side_effect = [
        # First call: list_chores query
        [
            {
                "id": "uuid-1",
                "title": "Dishes",
                "recurrence_pattern": "weekly",
                "rotation_group": "kitchen",
                "assignee_name": "Meral",
                "last_assignee_name": None,
            },
            {
                "id": "uuid-2",
                "title": "Vacuum living room",
                "recurrence_pattern": "biweekly",
                "rotation_group": None,
                "assignee_name": "Ruben",
                "last_assignee_name": None,
            },
        ],
        # Second call: _compute_fairness_nudge for kitchen group — balanced
        [],
    ]

    pool = _make_mock_pool(conn)

    with patch("app.tools.chores.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await list_chores()
        assert "Recurring chores:" in result
        assert "Dishes" in result
        assert "assigned to Meral" in result
        assert "[weekly]" in result
        assert "[kitchen]" in result
        assert "Vacuum living room" in result
        assert "assigned to Ruben" in result
        assert "[biweekly]" in result


@pytest.mark.asyncio
async def test_list_chores_empty():
    """No chores returns 'No recurring chores configured.'"""
    conn = AsyncMock()
    conn.fetch.return_value = []

    pool = _make_mock_pool(conn)

    with patch("app.tools.chores.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await list_chores()
        assert result == "No recurring chores configured."


@pytest.mark.asyncio
async def test_list_chores_with_fairness_nudge():
    """Mock chore_rotation_log to return 3 completions for Ruben, 1 for Meral;
    verify fair-share appears in output."""
    conn = AsyncMock()

    # First fetch: list chores (one chore with rotation_group='kitchen')
    conn.fetch.side_effect = [
        # First call: list_chores query
        [
            {
                "id": "uuid-1",
                "title": "Dishes",
                "recurrence_pattern": "weekly",
                "rotation_group": "kitchen",
                "assignee_name": "Meral",
                "last_assignee_name": None,
            },
        ],
        # Second call: _compute_fairness_nudge query
        [
            {"name": "Ruben", "count": 3},
            {"name": "Meral", "count": 1},
        ],
    ]

    pool = _make_mock_pool(conn)

    with patch("app.tools.chores.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await list_chores()
        assert "Recurring chores:" in result
        assert "⚖️ Fair-share:" in result
        assert "Ruben has done this 3x" in result
        assert "Meral has done this 1x" in result


@pytest.mark.asyncio
async def test_list_chores_filtered_by_rotation_group():
    """Uses rotation_group parameter in SQL WHERE clause."""
    conn = AsyncMock()
    conn.fetch.return_value = []

    pool = _make_mock_pool(conn)

    with patch("app.tools.chores.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await list_chores(rotation_group="kitchen")
        assert result == "No recurring chores configured."

        call_sql = conn.fetch.call_args[0][0]
        assert "rotation_group" in call_sql
        # Check parameter was passed
        call_params = conn.fetch.call_args[0][1:]
        assert "kitchen" in call_params


# ---------------------------------------------------------------------------
# complete_chore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_chore_rotates_assignee():
    """Recurring chore with rotation: mark done, verify INSERT of new instance
    with swapped assignee, verify rotation log INSERT.

    Query order in complete_chore:
    1. fetchrow: find chore by exact title
    2. fetchrow: user lookup for completed_by_uuid
    3. execute: UPDATE status='done'
    4. execute: INSERT into chore_rotation_log
    5. fetch: list household members for rotation
    6. fetchrow: get next assignee name
    7. fetchrow: user lookup for next_assignee_uuid
    8. execute: INSERT new chore instance
    9. fetch: fairness computation
    """
    conn = AsyncMock()
    conn.fetchrow.side_effect = [
        # 1. Find chore by exact title
        {
            "id": "chore-dishes",
            "title": "Dishes",
            "recurrence_pattern": "weekly",
            "rotation_group": "kitchen",
            "assignee_id": "uuid-ruben",
            "last_rotation_assignee_id": None,
        },
        # 2. User lookup for completed_by
        {"id": "uuid-meral"},
        # 7. Fetch next assignee UUID (called internally by _get_user_uuid)
        {"id": "uuid-ruben"},
    ]

    # Steps 3, 4, 8: executes
    conn.execute.side_effect = [
        "UPDATE 1",       # 3. mark done
        "INSERT 0 1",     # 4. rotation log
        "INSERT 0 1",     # 8. new chore instance
    ]

    # Step 5: fetch members for rotation
    conn.fetch.side_effect = [
        # 5. List household members
        [
            {"id": "uuid-ruben", "name": "Ruben"},
            {"id": "uuid-meral", "name": "Meral"},
        ],
        # 9. Fairness computation — returns empty (balanced)
        [],
    ]

    pool = _make_mock_pool(conn)

    with patch("app.tools.chores.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await complete_chore("Dishes", user="Meral")
        # Original assignee: Ruben, no last_rotation → flip from original → Meral
        assert "Completed chore 'Dishes'" in result
        assert "Next instance assigned to Meral" in result

        # Verify rotation log INSERT happened
        rotation_log_sql = conn.execute.call_args_list[1][0][0]
        assert "INSERT INTO chore_rotation_log" in rotation_log_sql

        # Verify new instance INSERT happened
        new_instance_sql = conn.execute.call_args_list[2][0][0]
        assert "INSERT INTO tasks" in new_instance_sql
        assert conn.execute.call_count >= 3


@pytest.mark.asyncio
async def test_complete_chore_fairness_nudge():
    """Mock rotation_log with imbalanced counts, verify nudge text in response.

    Query order:
    1. fetchrow: find chore
    2. fetchrow: user lookup
    3. execute: UPDATE
    4. execute: rotation log INSERT
    5. fetch: members
    6. fetchrow: next assignee name
    7. fetchrow: next assignee UUID
    8. execute: new instance INSERT
    9. fetch: fairness (with imbalanced data)
    """
    conn = AsyncMock()
    conn.fetchrow.side_effect = [
        # 1. Find chore
        {
            "id": "chore-dishes",
            "title": "Dishes",
            "recurrence_pattern": "weekly",
            "rotation_group": "kitchen",
            "assignee_id": "uuid-meral",
            "last_rotation_assignee_id": None,
        },
        # 2. User lookup
        {"id": "uuid-ruben"},
        # 7. Next assignee UUID lookup
        {"id": "uuid-meral"},
    ]

    conn.execute.side_effect = [
        "UPDATE 1",       # 3. mark done
        "INSERT 0 1",     # 4. rotation log
        "INSERT 0 1",     # 8. new chore instance
    ]

    conn.fetch.side_effect = [
        # 5. Members
        [
            {"id": "uuid-ruben", "name": "Ruben"},
            {"id": "uuid-meral", "name": "Meral"},
        ],
        # 9. Fairness — imbalanced
        [
            {"name": "Ruben", "count": 3},
            {"name": "Meral", "count": 1},
        ],
    ]

    pool = _make_mock_pool(conn)

    with patch("app.tools.chores.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await complete_chore("Dishes", user="Ruben")
        # Original assignee: Meral, no last_rotation → flip from original → Ruben
        assert "Completed chore 'Dishes'" in result
        assert "Next instance assigned to Ruben" in result
        assert "⚖️ Fair-share:" in result
        assert "Ruben has done this 3x" in result


@pytest.mark.asyncio
async def test_complete_chore_non_recurring():
    """Chore without recurrence just marks done, no new instance."""
    conn = AsyncMock()
    conn.fetchrow.side_effect = [
        # Find chore (non-recurring)
        {
            "id": "chore-onetime",
            "title": "Clean garage",
            "recurrence_pattern": None,
            "rotation_group": None,
            "assignee_id": "uuid-ruben",
            "last_rotation_assignee_id": None,
        },
        # User lookup for completed_by
        {"id": "uuid-ruben"},
    ]
    conn.execute.return_value = "UPDATE 1"

    pool = _make_mock_pool(conn)

    with patch("app.tools.chores.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await complete_chore("Clean garage", user="Ruben")
        assert result == "Completed chore 'Clean garage'."

        # Should have only executed one UPDATE — no rotation log or new INSERT
        assert conn.execute.call_count == 1


@pytest.mark.asyncio
async def test_complete_chore_not_found():
    """No match returns error."""
    conn = AsyncMock()
    conn.fetchrow.return_value = None  # both exact and ILIKE return None

    pool = _make_mock_pool(conn)

    with patch("app.tools.chores.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await complete_chore("Nonexistent", user="Ruben")
        assert "Could not find" in result
        assert conn.execute.call_count == 0
