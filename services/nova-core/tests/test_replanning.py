"""Tests for the replanning engine (Phase 44).

Covers risk scoring, capacity checks, next-best-action computation,
replan triggers, scheduler integration, dashboard SSE, and tool hooks.
"""
from __future__ import annotations

import json
import uuid as _uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.planning import PlannedBlock, TimeSlot


def _make_mock_pool(mock_conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = mock_conn
    return pool


def _tz_aware(year, month, day, hour, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


# ===================================================================
# Task 1: Risk scoring, capacity, next-action, replan triggers
# ===================================================================


class TestComputeRiskScore:
    def test_no_deadline_low_priority(self):
        """Risk < 0.4, level 'low' for low-priority tasks with no deadlines."""
        task = {"title": "Chill", "priority": "low", "task_duration_min": 30}
        result = compute_risk_score(task, [], [])
        assert result["score"] < 0.4
        assert result["level"] == "low"

    def test_overdue_critical(self):
        """Hard deadline in past -> score > 0.8, level 'critical'."""
        task = {
            "title": "Late",
            "priority": "high",
            "hard_deadline": _tz_aware(2024, 1, 1, 12, 0),
            "task_duration_min": 30,
        }
        result = compute_risk_score(task, [], [])
        assert result["score"] > 0.8
        assert result["level"] == "critical"
        assert any("Overdue" in f for f in result["factors"])

    def test_due_soon_high(self):
        """Due within 6h -> level 'high'."""
        soon = datetime.now(timezone.utc) + timedelta(hours=3)
        task = {
            "title": "Quick Task",
            "priority": "high",
            "due_at": soon,
            "task_duration_min": 60,
        }
        result = compute_risk_score(task, [], [])
        assert result["score"] > 0.6
        assert result["level"] in ("high", "critical")

    def test_no_deadline_medium_priority(self):
        """Medium priority with no deadlines -> medium risk."""
        task = {"title": "Normal", "priority": "medium", "task_duration_min": 30}
        result = compute_risk_score(task, [], [])
        assert result["level"] == "medium"

    def test_blocker_factor_adds_risk(self):
        """Task with blockers gets score bump."""
        soon = datetime.now(timezone.utc) + timedelta(hours=12)
        task = {
            "title": "Blocked",
            "priority": "low",
            "due_at": soon,
            "task_duration_min": 30,
            "has_blockers": True,
        }
        result = compute_risk_score(task, [], [])
        assert any("Blocked" in f for f in result["factors"])

    def test_long_task_duration_pressure(self):
        """Long task due within 48h gets duration pressure factor."""
        soon = datetime.now(timezone.utc) + timedelta(hours=30)
        task = {
            "title": "Big Doc",
            "priority": "medium",
            "due_at": soon,
            "task_duration_min": 180,
        }
        result = compute_risk_score(task, [], [])
        assert any("Long" in f for f in result["factors"])


class TestGetAtRiskTasks:
    @pytest.mark.asyncio
    async def test_empty_no_tasks(self):
        """No active tasks -> empty list."""
        conn = AsyncMock()
        conn.fetch.side_effect = [[], []]  # tasks + blockers
        pool = _make_mock_pool(conn)

        with patch("app.replanning.get_pool", new_callable=AsyncMock) as gp, \
             patch("app.replanning.load_blocks", new_callable=AsyncMock) as lb, \
             patch("app.replanning._fetch_calendar_events", new_callable=AsyncMock) as fce:
            gp.return_value = pool
            lb.return_value = []
            fce.return_value = []

            result = await get_at_risk_tasks("Ruben")
            assert result == []

    @pytest.mark.asyncio
    async def test_ordering_highest_risk_first(self):
        """Two tasks with different scores -> higher score first."""
        conn = AsyncMock()
        conn.fetch.side_effect = [
            [
                {"id": "1", "title": "Urgent", "priority": "high", "due_at": _tz_aware(2024, 6, 1, 0, 0),
                 "task_duration_min": 30, "earliest_start": None, "latest_end": None,
                 "hard_deadline": _tz_aware(2024, 6, 1, 0, 0), "soft_deadline": None,
                 "planning_state": None, "labels": None, "assignee_name": "Ruben"},
                {"id": "2", "title": "Later", "priority": "low", "due_at": None,
                 "task_duration_min": 30, "earliest_start": None, "latest_end": None,
                 "hard_deadline": None, "soft_deadline": None,
                 "planning_state": None, "labels": None, "assignee_name": "Ruben"},
            ],
            [],  # blockers
        ]
        pool = _make_mock_pool(conn)

        with patch("app.replanning.get_pool", new_callable=AsyncMock) as gp, \
             patch("app.replanning.load_blocks", new_callable=AsyncMock) as lb, \
             patch("app.replanning._fetch_calendar_events", new_callable=AsyncMock) as fce:
            gp.return_value = pool
            lb.return_value = []
            fce.return_value = []

            result = await get_at_risk_tasks("Ruben")
            assert len(result) == 2
            assert result[0]["score"] >= result[1]["score"]

    @pytest.mark.asyncio
    async def test_household_returns_all(self):
        """Household scope fetches tasks across all assignees."""
        conn = AsyncMock()
        conn.fetch.side_effect = [
            [
                {"id": "1", "title": "A", "priority": "high", "due_at": None,
                 "task_duration_min": 30, "earliest_start": None, "latest_end": None,
                 "hard_deadline": None, "soft_deadline": None,
                 "planning_state": None, "labels": None, "assignee_name": "Ruben"},
                {"id": "2", "title": "B", "priority": "medium", "due_at": None,
                 "task_duration_min": 30, "earliest_start": None, "latest_end": None,
                 "hard_deadline": None, "soft_deadline": None,
                 "planning_state": None, "labels": None, "assignee_name": "Meral"},
            ],
            [],
        ]
        pool = _make_mock_pool(conn)

        with patch("app.replanning.get_pool", new_callable=AsyncMock) as gp, \
             patch("app.replanning.load_blocks", new_callable=AsyncMock) as lb, \
             patch("app.replanning._fetch_calendar_events", new_callable=AsyncMock) as fce:
            gp.return_value = pool
            lb.return_value = []
            fce.return_value = []

            result = await get_at_risk_tasks("household")
            assert len(result) == 2


class TestComputeCapacityUtilization:
    @pytest.mark.asyncio
    async def test_empty_day_zero(self):
        """No blocks -> 0% utilization."""
        with patch("app.replanning.load_blocks", new_callable=AsyncMock) as lb, \
             patch("app.replanning._fetch_calendar_events", new_callable=AsyncMock) as fce, \
             patch("app.replanning.get_pool", new_callable=AsyncMock) as gp:
            lb.return_value = []
            fce.return_value = []
            gp.return_value = _make_mock_pool(AsyncMock())

            result = await compute_capacity_utilization("Ruben", date(2026, 7, 15), date(2026, 7, 15))
            assert result["per_day"][0]["utilization"] == 0.0

    @pytest.mark.asyncio
    async def test_full_day_high_utilization(self):
        """Blocks filling most of the day -> ~100%."""
        today = date.today()
        blocks = [
            PlannedBlock(
                planned_date=today,
                start_time=_tz_aware(today.year, today.month, today.day, 8, 0),
                end_time=_tz_aware(today.year, today.month, today.day, 21, 0),
                title="Full Day",
            ),
        ]
        with patch("app.replanning.load_blocks", new_callable=AsyncMock) as lb, \
             patch("app.replanning._fetch_calendar_events", new_callable=AsyncMock) as fce, \
             patch("app.replanning.get_pool", new_callable=AsyncMock) as gp:
            lb.return_value = blocks
            fce.return_value = []
            gp.return_value = _make_mock_pool(AsyncMock())

            result = await compute_capacity_utilization("Ruben", today, today)
            assert result["per_day"][0]["utilization"] > 0.9


class TestComputeNextBestAction:
    @pytest.mark.asyncio
    async def test_returns_highest_risk_task(self):
        """The highest-risk task that fits a slot is returned."""
        with patch("app.replanning.get_at_risk_tasks", new_callable=AsyncMock) as mock_risk, \
             patch("app.replanning.load_blocks", new_callable=AsyncMock) as lb, \
             patch("app.replanning._fetch_calendar_events", new_callable=AsyncMock) as fce, \
             patch("app.replanning.get_pool", new_callable=AsyncMock) as gp:
            mock_risk.return_value = [
                {"task_id": "1", "title": "Top Task", "assignee": "Ruben",
                 "level": "high", "score": 0.85, "duration_min": 30},
                {"task_id": "2", "title": "Low Task", "assignee": "Ruben",
                 "level": "low", "score": 0.2, "duration_min": 30},
            ]
            lb.return_value = []
            fce.return_value = []
            gp.return_value = _make_mock_pool(AsyncMock())

            result = await compute_next_best_action("Ruben")
            assert result["has_next_action"] is True
            assert result["task_id"] == "1"

    @pytest.mark.asyncio
    async def test_no_tasks_returns_empty(self):
        """No tasks -> has_next_action=False."""
        with patch("app.replanning.get_at_risk_tasks", new_callable=AsyncMock) as mock_risk:
            mock_risk.return_value = []

            result = await compute_next_best_action("Ruben")
            assert result["has_next_action"] is False


class TestReplanIfNeeded:
    @pytest.mark.asyncio
    async def test_triggers_on_conflict(self):
        """Event overlaps planned block -> returns True, generate_plan called."""
        affected = date(2026, 7, 15)
        blocks = [
            PlannedBlock(
                id="b1", is_occupied=False,
                planned_date=affected,
                start_time=_tz_aware(2026, 7, 15, 10, 0),
                end_time=_tz_aware(2026, 7, 15, 11, 0),
                title="Planned Work",
            ),
        ]
        events = [
            {"start": "2026-07-15T10:30:00+00:00", "end": "2026-07-15T11:30:00+00:00", "title": "Meeting"},
        ]

        with patch("app.replanning.get_pool", new_callable=AsyncMock) as gp, \
             patch("app.replanning.load_blocks", new_callable=AsyncMock) as lb, \
             patch("app.replanning._fetch_calendar_events", new_callable=AsyncMock) as fce, \
             patch("app.replanning.generate_plan", new_callable=AsyncMock) as mock_gen:
            pool = _make_mock_pool(AsyncMock())
            gp.return_value = pool
            lb.return_value = blocks
            fce.return_value = events

            result = await replan_if_needed("Ruben", affected, "test conflict")
            assert result is True
            mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_conflict_no_replan(self):
        """Event does not overlap -> returns False, generate_plan not called."""
        affected = date(2026, 7, 15)
        blocks = [
            PlannedBlock(
                id="b1", is_occupied=False,
                planned_date=affected,
                start_time=_tz_aware(2026, 7, 15, 9, 0),
                end_time=_tz_aware(2026, 7, 15, 10, 0),
                title="Planned Work",
            ),
        ]
        events = [
            {"start": "2026-07-15T14:00:00+00:00", "end": "2026-07-15T15:00:00+00:00", "title": "Later Meeting"},
        ]

        with patch("app.replanning.get_pool", new_callable=AsyncMock) as gp, \
             patch("app.replanning.load_blocks", new_callable=AsyncMock) as lb, \
             patch("app.replanning._fetch_calendar_events", new_callable=AsyncMock) as fce, \
             patch("app.replanning.generate_plan", new_callable=AsyncMock) as mock_gen:
            pool = _make_mock_pool(AsyncMock())
            gp.return_value = pool
            lb.return_value = blocks
            fce.return_value = events

            result = await replan_if_needed("Ruben", affected, "test no conflict")
            assert result is False
            mock_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_occupied_block_ignored(self):
        """An is_occupied block should not trigger replan even if it overlaps."""
        affected = date(2026, 7, 15)
        blocks = [
            PlannedBlock(
                id="b1", is_occupied=True,
                planned_date=affected,
                start_time=_tz_aware(2026, 7, 15, 10, 0),
                end_time=_tz_aware(2026, 7, 15, 11, 0),
                title="Occupied Slot",
            ),
        ]
        events = [
            {"start": "2026-07-15T10:30:00+00:00", "end": "2026-07-15T11:30:00+00:00", "title": "Meeting"},
        ]

        with patch("app.replanning.get_pool", new_callable=AsyncMock) as gp, \
             patch("app.replanning.load_blocks", new_callable=AsyncMock) as lb, \
             patch("app.replanning._fetch_calendar_events", new_callable=AsyncMock) as fce, \
             patch("app.replanning.generate_plan", new_callable=AsyncMock) as mock_gen:
            pool = _make_mock_pool(AsyncMock())
            gp.return_value = pool
            lb.return_value = blocks
            fce.return_value = events

            result = await replan_if_needed("Ruben", affected, "occupied test")
            assert result is False
            mock_gen.assert_not_called()


class TestReplanAfterTaskChange:
    @pytest.mark.asyncio
    async def test_triggers_when_due_within_7d(self):
        """Task with due_at within 7d -> returns True, generate_plan called."""
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            "due_at": _tz_aware(2026, 7, 18, 12, 0),
            "planning_state": "unscheduled",
        }
        pool = _make_mock_pool(conn)

        with patch("app.replanning.get_pool", new_callable=AsyncMock) as gp, \
             patch("app.replanning.generate_plan", new_callable=AsyncMock) as mock_gen:
            gp.return_value = pool

            result = await replan_after_task_change("Ruben", "task-1", "test")
            assert result is True
            mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_triggers_when_scheduled(self):
        """Task with planning_state='scheduled' -> returns True."""
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            "due_at": None,
            "planning_state": "scheduled",
        }
        pool = _make_mock_pool(conn)

        with patch("app.replanning.get_pool", new_callable=AsyncMock) as gp, \
             patch("app.replanning.generate_plan", new_callable=AsyncMock) as mock_gen:
            gp.return_value = pool

            result = await replan_after_task_change("Ruben", "task-1", "test")
            assert result is True
            mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_trigger_for_distant_task(self):
        """Task with due_at far in the future -> returns False."""
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            "due_at": _tz_aware(2030, 1, 1, 12, 0),
            "planning_state": "unscheduled",
        }
        pool = _make_mock_pool(conn)

        with patch("app.replanning.get_pool", new_callable=AsyncMock) as gp, \
             patch("app.replanning.generate_plan", new_callable=AsyncMock) as mock_gen:
            gp.return_value = pool

            result = await replan_after_task_change("Ruben", "task-1", "test")
            assert result is False
            mock_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_trigger_for_nonexistent_task(self):
        """Task not found -> returns False."""
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        pool = _make_mock_pool(conn)

        with patch("app.replanning.get_pool", new_callable=AsyncMock) as gp, \
             patch("app.replanning.generate_plan", new_callable=AsyncMock) as mock_gen:
            gp.return_value = pool

            result = await replan_after_task_change("Ruben", "nonexistent", "test")
            assert result is False
            mock_gen.assert_not_called()


# ===================================================================
# Task 2: Scheduler integration and dashboard SSE
# ===================================================================


class TestCheckAtRiskTasks:
    @pytest.mark.asyncio
    async def test_sends_alert_for_high_risk(self):
        """A task with risk 'high' triggers a proactive alert."""
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [{"name": "Ruben"}, {"name": "Meral"}]
        pool = _make_mock_pool(mock_conn)

        with patch("app.scheduler.get_at_risk_tasks", new_callable=AsyncMock) as mock_risk, \
             patch("app.scheduler.send_to_user", new_callable=AsyncMock) as mock_send, \
             patch("app.scheduler.get_pool", new_callable=AsyncMock) as mock_gp:
            mock_gp.return_value = pool
            mock_risk.return_value = [
                {"title": "Urgent Report", "level": "high", "score": 0.7, "factors": ["Due today"]}
            ]

            from app.scheduler import check_at_risk_tasks
            await check_at_risk_tasks()

            assert mock_send.call_count >= 1

    @pytest.mark.asyncio
    async def test_no_risk_no_alerts(self):
        """No at-risk tasks -> no alerts."""
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [{"name": "Ruben"}]
        pool = _make_mock_pool(mock_conn)

        with patch("app.scheduler.get_at_risk_tasks", new_callable=AsyncMock) as mock_risk, \
             patch("app.scheduler.send_to_user", new_callable=AsyncMock) as mock_send, \
             patch("app.scheduler.get_pool", new_callable=AsyncMock) as mock_gp:
            mock_gp.return_value = pool
            mock_risk.return_value = []

            from app.scheduler import check_at_risk_tasks
            await check_at_risk_tasks()

            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_overdue_tasks_delegates(self):
        """Old check_overdue_tasks delegates to check_at_risk_tasks."""
        with patch("app.scheduler.check_at_risk_tasks", new_callable=AsyncMock) as mock_check:
            from app.scheduler import check_overdue_tasks
            await check_overdue_tasks()

            mock_check.assert_called_once()


class TestMorningBriefing:
    @pytest.mark.asyncio
    async def test_includes_risk_and_next_action(self):
        """send_morning_briefing_for_user includes 'At Risk' and 'Next Action' sections."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"id": _uuid.UUID("00000000-0000-0000-0000-000000000010")}
        mock_conn.fetch.return_value = []
        pool = _make_mock_pool(mock_conn)

        with patch("app.scheduler.send_to_user", new_callable=AsyncMock) as mock_send, \
             patch("app.scheduler.fetch_emails_imap", new_callable=AsyncMock, return_value=[]), \
             patch("app.scheduler.classify_importance", new_callable=AsyncMock, return_value=False), \
             patch("app.scheduler.get_pool", new_callable=AsyncMock) as mock_gp, \
             patch("app.scheduler._get_calendar") as mock_cal, \
             patch("app.scheduler.get_user_memories", new_callable=AsyncMock, return_value=""), \
             patch("app.scheduler.get_at_risk_tasks", new_callable=AsyncMock) as mock_risk, \
             patch("app.scheduler.compute_next_best_action", new_callable=AsyncMock) as mock_nba, \
             patch("app.planning.load_blocks", new_callable=AsyncMock) as mock_lb:

            mock_gp.return_value = pool
            mock_cal.return_value = MagicMock()
            mock_cal.return_value.search.return_value = []
            mock_lb.return_value = []
            mock_risk.return_value = [
                {"title": "Due Report", "level": "high", "score": 0.75, "factors": ["Due today"]}
            ]
            mock_nba.return_value = {
                "has_next_action": True,
                "title": "Due Report",
                "recommended_slot": {"date": "2026-07-15", "start": "14:00", "end": "15:00"},
                "reasoning": "Due today, high priority.",
            }

            from app.scheduler import send_morning_briefing_for_user
            await send_morning_briefing_for_user("Ruben")

            sent_text = mock_send.call_args[0][1]
            assert "At Risk" in sent_text
            assert "Due Report" in sent_text
            assert "Next Action" in sent_text


class TestWeeklyBriefing:
    @pytest.mark.asyncio
    async def test_includes_risk(self):
        """send_weekly_briefing_for_user includes 'At Risk This Week' section."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"id": _uuid.UUID("00000000-0000-0000-0000-000000000010")}
        mock_conn.fetch.return_value = []
        pool = _make_mock_pool(mock_conn)

        with patch("app.scheduler.send_to_user", new_callable=AsyncMock) as mock_send, \
             patch("app.scheduler.fetch_emails_imap", new_callable=AsyncMock, return_value=[]), \
             patch("app.scheduler.classify_importance", new_callable=AsyncMock, return_value=False), \
             patch("app.scheduler.get_pool", new_callable=AsyncMock) as mock_gp, \
             patch("app.scheduler._get_calendar") as mock_cal, \
             patch("app.scheduler.get_user_memories", new_callable=AsyncMock, return_value=""), \
             patch("app.scheduler.get_at_risk_tasks", new_callable=AsyncMock) as mock_risk, \
             patch("app.scheduler.compute_next_best_action", new_callable=AsyncMock) as mock_nba, \
             patch("app.planning.load_blocks", new_callable=AsyncMock) as mock_lb:

            mock_gp.return_value = pool
            mock_cal.return_value = MagicMock()
            mock_cal.return_value.search.return_value = []
            mock_lb.return_value = []
            mock_risk.return_value = [
                {"title": "Big Project", "level": "high", "score": 0.72, "factors": ["Hard deadline Fri"]}
            ]
            mock_nba.return_value = {"has_next_action": True, "title": "Big Project"}

            from app.scheduler import send_weekly_briefing_for_user
            await send_weekly_briefing_for_user("Ruben")

            sent_text = mock_send.call_args[0][1]
            assert "At Risk This Week" in sent_text
            assert "Big Project" in sent_text
            assert "Next Action" in sent_text


class TestDashboardSSE:
    @pytest.mark.asyncio
    async def test_includes_risk_payload(self):
        """SSE payload includes at_risk and next_action fields."""
        with patch("app.main.dashboard_tasks", new_callable=AsyncMock) as mock_tasks, \
             patch("app.main.dashboard_events", new_callable=AsyncMock) as mock_events, \
             patch("app.main.dashboard_audit", new_callable=AsyncMock) as mock_audit, \
             patch("app.planning.load_blocks", new_callable=AsyncMock) as mock_blocks, \
             patch("app.replanning.get_at_risk_tasks", new_callable=AsyncMock) as mock_risk, \
             patch("app.replanning.compute_next_best_action", new_callable=AsyncMock) as mock_nba:

            mock_tasks.return_value = {"tasks": []}
            mock_events.return_value = {"events": []}
            mock_audit.return_value = {"audit": []}
            mock_blocks.return_value = []
            mock_risk.return_value = {"Ruben": [{"title": "Late Task", "level": "critical", "score": 0.9}]}
            mock_nba.return_value = {"has_next_action": True, "title": "Late Task"}

            from app.main import dashboard_stream
            resp = await dashboard_stream()
            async for chunk in resp.body_iterator:
                data_str = chunk.removeprefix("data: ")
                payload = json.loads(data_str)
                assert "at_risk" in payload
                assert "next_action" in payload
                break


# ===================================================================
# Task 3: Calendar and task mutation hooks
# ===================================================================


class TestCreateEventHook:
    @pytest.mark.asyncio
    async def test_triggers_replan(self):
        """Creating a calendar event triggers replan_if_needed."""
        with patch("app.tools.calendar._get_calendar") as mock_cal, \
             patch("app.tools.calendar.detect_conflicts", new_callable=AsyncMock, return_value=[]) as mock_dc, \
             patch("app.tools.calendar.replan_if_needed", new_callable=AsyncMock) as mock_replan:

            mock_cal_instance = MagicMock()
            mock_cal.return_value = mock_cal_instance

            from app.tools.calendar import create_event
            result = await create_event(
                title="Test Event",
                start="2026-07-20T10:00:00+02:00",
                end="2026-07-20T11:00:00+02:00",
            )

            assert "Created event" in result
            mock_replan.assert_called_once()


class TestAddTaskHook:
    @pytest.mark.asyncio
    async def test_triggers_replan_with_planning_metadata(self):
        """Adding a task with planning metadata triggers replan."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.side_effect = [
            _uuid.UUID("00000000-0000-0000-0000-000000000001"),
            _uuid.UUID("00000000-0000-0000-0000-000000000001"),
            _uuid.UUID("00000000-0000-0000-0000-000000000010"),
        ]
        mock_conn.fetchrow.return_value = None
        pool = _make_mock_pool(mock_conn)

        with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as mock_gp, \
             patch("app.tools.tasks.replan_after_task_change", new_callable=AsyncMock) as mock_replan:
            mock_gp.return_value = pool

            from app.tools.tasks import add_task
            result = await add_task(
                title="New Task",
                user="Ruben",
                task_duration_min=30,
            )

            assert "Added task" in result
            mock_replan.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_replan_without_planning_metadata(self):
        """Adding a bare task WITHOUT planning metadata does NOT trigger replan."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.side_effect = [
            _uuid.UUID("00000000-0000-0000-0000-000000000001"),
            _uuid.UUID("00000000-0000-0000-0000-000000000001"),
            _uuid.UUID("00000000-0000-0000-0000-000000000010"),
        ]
        mock_conn.fetchrow.return_value = None
        pool = _make_mock_pool(mock_conn)

        with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as mock_gp, \
             patch("app.tools.tasks.replan_after_task_change", new_callable=AsyncMock) as mock_replan:
            mock_gp.return_value = pool

            from app.tools.tasks import add_task
            result = await add_task(
                title="Quick Note",
                user="Ruben",
            )

            assert "Added task" in result
            mock_replan.assert_not_called()


class TestCompleteTaskHook:
    @pytest.mark.asyncio
    async def test_triggers_replan(self):
        """Completing a task triggers replan_after_task_change."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.side_effect = [
            _uuid.UUID("00000000-0000-0000-0000-000000000001"),
            "Ruben",
        ]
        mock_conn.fetch.return_value = []
        pool = _make_mock_pool(mock_conn)

        with patch("app.tools.tasks.get_pool", new_callable=AsyncMock) as mock_gp, \
             patch("app.tools.tasks.replan_after_task_change", new_callable=AsyncMock) as mock_replan:
            mock_gp.return_value = pool

            from app.tools.tasks import complete_task
            result = await complete_task(title="Test Task")

            assert "Marked" in result
            mock_replan.assert_called_once()


# Import functions under test at module level after class definitions
# so they pick up the correct mock targets.
from app.replanning import (  # noqa: E402
    compute_risk_score,
    get_at_risk_tasks,
    compute_capacity_utilization,
    compute_next_best_action,
    replan_if_needed,
    replan_after_task_change,
)
