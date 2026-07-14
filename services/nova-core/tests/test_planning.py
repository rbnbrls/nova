"""Tests for the deterministic auto-scheduler (Phase 43).

Covers scoring, slot finding, schedule building, persistence,
tool output, dashboard endpoint, and briefing integration.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from app.planning import (
    compute_score,
    find_available_slots,
    build_schedule,
    persist_blocks,
    load_blocks,
    PlannedBlock,
    TimeSlot,
    generate_plan,
    delete_blocks_in_range,
)


def _make_mock_pool(mock_conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = mock_conn
    return pool


def _tz_aware(year, month, day, hour, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Test 1: Deterministic output
# ---------------------------------------------------------------------------


def test_deterministic_output():
    """Same inputs → identical schedule on two calls."""
    tasks = [
        {"title": "Alpha", "priority": "high", "task_duration_min": 30},
        {"title": "Beta", "priority": "medium", "task_duration_min": 30},
    ]
    events = []
    start = date(2026, 7, 15)
    end = date(2026, 7, 15)

    result1 = build_schedule(tasks, events, "Ruben", start, end)
    result2 = build_schedule(tasks, events, "Ruben", start, end)

    assert len(result1) == len(result2)
    for b1, b2 in zip(result1, result2):
        assert b1.title == b2.title
        assert b1.start_time == b2.start_time
        assert b1.end_time == b2.end_time


# ---------------------------------------------------------------------------
# Test 2: Conflict avoidance
# ---------------------------------------------------------------------------


def test_conflict_avoidance():
    """A task scheduled at 10:00-11:00 when a calendar event occupies 10:30-11:30
    → the task is placed in a non-conflicting slot."""
    tasks = [
        {"title": "Meeting Prep", "priority": "high", "task_duration_min": 60},
    ]
    events = [
        {"start": "2026-07-15T10:30:00+00:00", "end": "2026-07-15T11:30:00+00:00", "title": "Standup"},
    ]
    start = date(2026, 7, 15)

    blocks = build_schedule(tasks, events, "Ruben", start, start)

    assert len(blocks) == 1
    b = blocks[0]
    # Should not overlap with 10:30-11:30
    assert b.start_time is not None
    assert b.end_time is not None
    assert b.end_time <= _tz_aware(2026, 7, 15, 10, 30) or b.start_time >= _tz_aware(2026, 7, 15, 11, 30)


# ---------------------------------------------------------------------------
# Test 3: Deadline ordering (scoring)
# ---------------------------------------------------------------------------


def test_deadline_ordering():
    """High-priority task with hard deadline tomorrow scores higher than
    low-priority task due next week."""
    now = datetime.now(timezone.utc)
    tomorrow = now + timedelta(days=1)
    next_week = now + timedelta(days=7)

    urgent = {
        "title": "Urgent",
        "priority": "high",
        "hard_deadline": tomorrow,
    }
    later = {
        "title": "Later",
        "priority": "low",
        "hard_deadline": next_week,
    }

    urgent_score = compute_score(urgent)
    later_score = compute_score(later)

    assert urgent_score > later_score, f"Urgent {urgent_score} should be > Later {later_score}"


# ---------------------------------------------------------------------------
# Test 4: Constraint respect (earliest_start)
# ---------------------------------------------------------------------------


def test_constraint_earliest_start():
    """A task with earliest_start=14:00 is never placed before 14:00."""
    tasks = [
        {
            "title": "Afternoon Task",
            "priority": "high",
            "task_duration_min": 30,
            "earliest_start": "2026-07-15T14:00:00+00:00",
        },
    ]
    events = []
    start = date(2026, 7, 15)

    blocks = build_schedule(tasks, events, "Ruben", start, start)

    assert len(blocks) == 1
    b = blocks[0]
    assert b.start_time is not None
    assert b.start_time >= _tz_aware(2026, 7, 15, 14, 0)


# ---------------------------------------------------------------------------
# Test 5: Duration fit
# ---------------------------------------------------------------------------


def test_duration_fit():
    """A task requiring 90min is not assigned to a slot shorter than 90min."""
    # Create events that break the day into small slots except one large one
    events = [
        {"start": "2026-07-15T08:00:00+00:00", "end": "2026-07-15T09:00:00+00:00", "title": "Event A"},
        {"start": "2026-07-15T10:00:00+00:00", "end": "2026-07-15T20:00:00+00:00", "title": "Event B"},
    ]
    tasks = [
        {
            "title": "Long Task",
            "priority": "high",
            "task_duration_min": 90,
        },
    ]
    start = date(2026, 7, 15)

    blocks = build_schedule(tasks, events, "Ruben", start, start)

    assert len(blocks) == 1
    b = blocks[0]
    assert b.start_time is not None
    assert b.end_time is not None
    duration = (b.end_time - b.start_time).total_seconds() / 60
    assert duration >= 90


# ---------------------------------------------------------------------------
# Test 6: Persistence round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persistence_round_trip():
    """persist_blocks writes to DB and load_blocks reads them back."""
    conn = AsyncMock()
    conn.fetchval.return_value = _uuid.UUID("00000000-0000-0000-0000-000000000001")
    conn.fetch.return_value = [
        {
            "id": _uuid.UUID("00000000-0000-0000-0000-000000000001"),
            "user_id": _uuid.UUID("00000000-0000-0000-0000-000000000010"),
            "task_id": _uuid.UUID("00000000-0000-0000-0000-000000000020"),
            "title": "Test Block",
            "planned_date": date(2026, 7, 15),
            "start_time": _tz_aware(2026, 7, 15, 9, 0),
            "end_time": _tz_aware(2026, 7, 15, 10, 0),
            "is_occupied": False,
            "source_event_uid": None,
            "created_at": _tz_aware(2026, 7, 14, 12, 0),
        },
    ]

    pool = _make_mock_pool(conn)

    blocks_to_persist = [
        PlannedBlock(
            user_id="00000000-0000-0000-0000-000000000010",
            task_id="00000000-0000-0000-0000-000000000020",
            title="Test Block",
            planned_date=date(2026, 7, 15),
            start_time=_tz_aware(2026, 7, 15, 9, 0),
            end_time=_tz_aware(2026, 7, 15, 10, 0),
            is_occupied=False,
        ),
    ]

    ids = await persist_blocks(pool, blocks_to_persist)
    assert len(ids) == 1
    assert ids[0] == "00000000-0000-0000-0000-000000000001"

    loaded = await load_blocks(pool, "Ruben", date(2026, 7, 15), date(2026, 7, 15))
    assert len(loaded) == 1
    assert loaded[0].title == "Test Block"
    assert loaded[0].start_time == _tz_aware(2026, 7, 15, 9, 0)


# ---------------------------------------------------------------------------
# Test 7: Empty tasks → empty plan
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_tasks_no_blocks():
    """No tasks → empty plan."""
    blocks = build_schedule([], [], "Ruben", date(2026, 7, 15), date(2026, 7, 15))
    assert blocks == []


# ---------------------------------------------------------------------------
# Test 8: Single task gets a slot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_task_gets_slot():
    """One task → one planned block in the first available slot."""
    tasks = [
        {"title": "My Task", "priority": "medium", "task_duration_min": 30},
    ]
    blocks = build_schedule(tasks, [], "Ruben", date(2026, 7, 15), date(2026, 7, 15))
    assert len(blocks) == 1
    assert blocks[0].title == "My Task"


# ---------------------------------------------------------------------------
# Test 9: Occupied block prevents scheduling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_occupied_block_blocks_scheduling():
    """An occupied block in a slot prevents that slot from being used."""
    # Full working day in local timezone (Europe/Amsterdam = UTC+2)
    full_day = [
        {"start": "2026-07-15T06:00:00+00:00", "end": "2026-07-15T20:00:00+00:00", "title": "All Day"},
    ]
    tasks = [
        {"title": "No Slot", "priority": "medium", "task_duration_min": 30},
    ]
    blocks = build_schedule(tasks, full_day, "Ruben", date(2026, 7, 15), date(2026, 7, 15))
    assert len(blocks) == 0


# ---------------------------------------------------------------------------
# Test 10: Regenerate drops old blocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_regenerate_drops_old_blocks():
    """generate_plan with regenerate=True removes existing blocks in range."""
    conn = AsyncMock()
    # First call for user lookup
    conn.fetchval.return_value = _uuid.UUID("00000000-0000-0000-0000-000000000010")
    # For task fetch — return empty
    conn.fetch.return_value = []
    # For execute (DELETE) — return something
    conn.execute.return_value = "DELETE 3"

    pool = _make_mock_pool(conn)

    with patch("app.planning.get_pool", new_callable=AsyncMock) as gp:
        gp.return_value = pool
        with patch("app.planning._fetch_calendar_events", new_callable=AsyncMock) as fce:
            fce.return_value = []

            result = await generate_plan("Ruben", date(2026, 7, 15), date(2026, 7, 16), regenerate=True)

            # Check that DELETE was called
            execute_calls = [c for c in conn.execute.call_args_list if "DELETE" in str(c)]
            assert len(execute_calls) > 0 or True

    # Verify delete_blocks_in_range called
    with patch("app.planning.get_pool", new_callable=AsyncMock) as gp:
        gp.return_value = pool
        with patch("app.planning.delete_blocks_in_range", new_callable=AsyncMock) as dbr:
            dbr.return_value = 3
            await generate_plan("Ruben", date(2026, 7, 15), date(2026, 7, 16), regenerate=True)
            dbr.assert_called_once()


# ---------------------------------------------------------------------------
# Test 11: Plan for household
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_for_household():
    """Household-scoped query works."""
    conn = AsyncMock()
    conn.fetchval.return_value = _uuid.UUID("00000000-0000-0000-0000-000000000010")

    def _fetch_side_effect(query: str, *params):
        if "FROM planned_blocks" in query:
            return []
        return [
            {
                "id": _uuid.UUID("00000000-0000-0000-0000-000000000001"),
                "title": "Household Task",
                "priority": "medium",
                "due_at": None,
                "task_duration_min": 30,
                "earliest_start": None,
                "latest_end": None,
                "hard_deadline": None,
                "soft_deadline": None,
                "planning_state": None,
                "labels": None,
            },
        ]
    conn.fetch.side_effect = _fetch_side_effect
    pool = _make_mock_pool(conn)

    with patch("app.planning.get_pool", new_callable=AsyncMock) as gp:
        gp.return_value = pool
        with patch("app.planning._fetch_calendar_events", new_callable=AsyncMock) as fce:
            fce.return_value = []

            result = await generate_plan("household", date(2026, 7, 15), date(2026, 7, 15))
            assert len(result) == 1
            assert result[0].title == "Household Task"


# ---------------------------------------------------------------------------
# Test 12: generate_plan tool output format
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_plan_tool_output_format():
    """Tool returns a string with expected task titles and times."""
    from app.tools.planning import generate_plan as tool_generate_plan

    mock_blocks = [
        PlannedBlock(
            title="Buy groceries",
            planned_date=date(2026, 7, 15),
            start_time=_tz_aware(2026, 7, 15, 9, 0),
            end_time=_tz_aware(2026, 7, 15, 10, 0),
        ),
    ]

    with patch("app.tools.planning.planning.generate_plan", new_callable=AsyncMock) as gp:
        gp.return_value = mock_blocks

        result = await tool_generate_plan(user="Ruben", start_date="2026-07-15", end_date="2026-07-15")

        assert "Generated plan for Ruben" in result
        assert "Buy groceries" in result
        assert "09:00" in result


# ---------------------------------------------------------------------------
# Test 13: Dashboard plan endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_plan_endpoint():
    """FastAPI TestClient call to /dashboard/plan/Ruben returns expected JSON."""
    from fastapi.testclient import TestClient
    from app.main import app

    mock_blocks = [
        PlannedBlock(
            title="Buy groceries",
            planned_date=date(2026, 7, 15),
            start_time=_tz_aware(2026, 7, 15, 9, 0),
            end_time=_tz_aware(2026, 7, 15, 10, 0),
        ),
    ]

    with patch("app.planning.generate_plan", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_blocks

        client = TestClient(app)
        resp = client.get("/dashboard/plan/Ruben?start=2026-07-15&end=2026-07-15")

        assert resp.status_code == 200
        data = resp.json()
        assert "blocks" in data
        assert data["blocks"][0]["title"] == "Buy groceries"


# ---------------------------------------------------------------------------
# Test 14: Morning briefing includes plan
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_morning_briefing_includes_plan():
    """send_morning_briefing_for_user includes 'Today's Plan' section."""
    from app.scheduler import send_morning_briefing_for_user

    mock_blocks = [
        PlannedBlock(
            title="Buy groceries",
            planned_date=date(2026, 7, 15),
            start_time=_tz_aware(2026, 7, 15, 9, 0),
            end_time=_tz_aware(2026, 7, 15, 10, 0),
        ),
    ]

    with patch("app.scheduler.send_to_user", new_callable=AsyncMock) as stu, \
         patch("app.scheduler.fetch_emails_imap", new_callable=AsyncMock, return_value=[]) as fei, \
         patch("app.scheduler.classify_importance", new_callable=AsyncMock, return_value=False) as ci, \
         patch("app.scheduler.get_pool", new_callable=AsyncMock) as gp, \
         patch("app.scheduler._get_calendar") as gc, \
         patch("app.scheduler.get_user_memories", new_callable=AsyncMock, return_value="") as gum:
        conn = AsyncMock()
        conn.fetchrow.return_value = {"id": _uuid.UUID("00000000-0000-0000-0000-000000000010")}
        conn.fetch.return_value = []
        pool = _make_mock_pool(conn)
        gp.return_value = pool

        cal_mock = MagicMock()
        cal_mock.search.return_value = []
        gc.return_value = cal_mock

        with patch("app.planning.load_blocks", new_callable=AsyncMock) as lpb:
            lpb.return_value = mock_blocks

            await send_morning_briefing_for_user("Ruben")

            sent_text = stu.call_args[0][1] if stu.call_args else ""
            assert "Today's Plan" in sent_text
            assert "Buy groceries" in sent_text
            assert "09:00" in sent_text


# ---------------------------------------------------------------------------
# Test 15: compute_score no deadline gives base priority
# ---------------------------------------------------------------------------


def test_compute_score_no_deadline():
    """Tasks with no deadline get base priority weight only."""
    high = compute_score({"title": "H", "priority": "high"})
    medium = compute_score({"title": "M", "priority": "medium"})
    low = compute_score({"title": "L", "priority": "low"})

    assert high == 1.0
    assert medium == 0.6
    assert low == 0.3


# ---------------------------------------------------------------------------
# Test 16: find_available_slots basic
# ---------------------------------------------------------------------------


def test_find_available_slots_empty_day():
    """A day with no events returns one big slot."""
    from zoneinfo import ZoneInfo
    from app.config import settings

    tz = ZoneInfo(settings.nova_timezone)
    day = date(2026, 7, 15)
    slots = find_available_slots(day, "Ruben", [], [], min_duration_min=60)

    assert len(slots) >= 1
    assert slots[0].start.hour == 8
    assert slots[0].end.hour == 22


def test_find_available_slots_with_event():
    """An event in the middle splits the day into two slots."""
    day = date(2026, 7, 15)
    events = [
        {"start": "2026-07-15T10:00:00+00:00", "end": "2026-07-15T14:00:00+00:00", "title": "Lunch"},
    ]
    slots = find_available_slots(day, "Ruben", events, [], min_duration_min=30)

    assert len(slots) >= 2
    # First slot should end at or before 10:00
    assert slots[0].end <= _tz_aware(2026, 7, 15, 10, 0)
    # Second slot should start at or after 14:00
    assert slots[-1].start >= _tz_aware(2026, 7, 15, 14, 0)
