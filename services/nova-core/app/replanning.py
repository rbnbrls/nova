"""Replanning engine: risk scoring, capacity checks, next-best-action computation, and change-triggered replan helpers.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from .config import settings
from .db import get_pool
from .planning import (
    WORK_DAY_START,
    WORK_DAY_END,
    PlannedBlock,
    _parse_dt,
    _fetch_calendar_events,
    compute_score,
    find_available_slots,
    generate_plan,
    load_blocks,
)

log = logging.getLogger("nova-core.replanning")


# ---------------------------------------------------------------------------
# 1. Risk scoring
# ---------------------------------------------------------------------------


def compute_risk_score(
    task: dict,
    blocks: list[PlannedBlock],
    calendar_events: list[dict],
) -> dict:
    """Produce a per-task risk assessment dict.

    Returns dict with keys: task_id, title, assignee, score, level, factors,
    due_at, hard_deadline, duration_min.
    """
    base = compute_score(task)
    score = base
    factors: list[str] = []
    now = datetime.now(timezone.utc)

    hard_deadline = task.get("hard_deadline")
    hd_dt = _parse_dt(hard_deadline) if isinstance(hard_deadline, str) else (hard_deadline if isinstance(hard_deadline, datetime) else None)
    if hd_dt is None and hard_deadline is not None and not isinstance(hard_deadline, str):
        hd_dt = hard_deadline

    due_at = task.get("due_at")
    da_dt = _parse_dt(due_at) if isinstance(due_at, str) else (due_at if isinstance(due_at, datetime) else None)
    if da_dt is None and due_at is not None and not isinstance(due_at, str):
        da_dt = due_at

    # Overdue penalty
    if isinstance(hd_dt, datetime) and hd_dt < now:
        overdue_delta = now - hd_dt
        score += 0.25
        days_over = max(1, overdue_delta.days)
        factors.append(f"Overdue by {days_over} day{'s' if days_over != 1 else ''}")

    # Due-today proximity
    if isinstance(da_dt, datetime):
        delta = da_dt - now
        if timedelta(0) < delta < timedelta(hours=24):
            remaining_hours = delta.total_seconds() / 3600
            duration_min = task.get("task_duration_min") or 60
            if remaining_hours < duration_min / 60:
                score += 0.15
                factors.append(
                    f"Due today, remaining time ({remaining_hours:.0f}h) "
                    f"less than duration ({duration_min}min)"
                )

    # Capacity factor
    deadline = hd_dt or da_dt
    if isinstance(deadline, datetime):
        capacity = _estimate_day_capacity(blocks, calendar_events, deadline.date())
        if capacity > 0.8:
            score += 0.10
            factors.append(f"Schedule is {capacity:.0%} full on deadline day")

    # Blocker factor
    if task.get("has_blockers"):
        score += 0.10
        factors.append("Blocked by incomplete dependencies")

    # Duration pressure
    duration_min = task.get("task_duration_min") or 60
    if duration_min > 120 and isinstance(deadline, datetime):
        deadline_delta = deadline - now
        if timedelta(0) < deadline_delta < timedelta(hours=48):
            score += 0.05
            factors.append(f"Long task ({duration_min}min) due within 48h")

    score = max(0.0, min(1.0, score))

    if score > 0.8:
        level = "critical"
    elif score > 0.6:
        level = "high"
    elif score > 0.3:
        level = "medium"
    else:
        level = "low"

    if not factors:
        factors.append(f"Base urgency score: {base:.2f}")

    return {
        "task_id": str(task.get("id", "")),
        "title": task.get("title", ""),
        "assignee": task.get("assignee_name", ""),
        "score": round(score, 2),
        "level": level,
        "factors": factors,
        "due_at": due_at.isoformat() if isinstance(due_at, datetime) else str(due_at or ""),
        "hard_deadline": hard_deadline.isoformat() if isinstance(hard_deadline, datetime) else str(hard_deadline or ""),
        "duration_min": task.get("task_duration_min") or 60,
    }


def _estimate_day_capacity(
    blocks: list[PlannedBlock],
    calendar_events: list[dict],
    target_date: date,
) -> float:
    """Return 0.0-1.0 how full *target_date* is (planned + events vs working day)."""
    day_start = datetime.combine(target_date, time(WORK_DAY_START, 0, 0), tzinfo=timezone.utc)
    day_end = datetime.combine(target_date, time(WORK_DAY_END, 0, 0), tzinfo=timezone.utc)
    total_minutes = (WORK_DAY_END - WORK_DAY_START) * 60

    occupied_minutes = 0.0
    for ev in calendar_events:
        ev_start = _parse_dt(ev.get("start", ""))
        ev_end = _parse_dt(ev.get("end", ""))
        if ev_start and ev_end and ev_start.date() == target_date:
            overlap_start = max(ev_start, day_start)
            overlap_end = min(ev_end, day_end)
            if overlap_start < overlap_end:
                occupied_minutes += (overlap_end - overlap_start).total_seconds() / 60

    planned_minutes = 0.0
    for b in blocks:
        if b.planned_date == target_date and b.start_time and b.end_time:
            overlap_start = max(b.start_time, day_start)
            overlap_end = min(b.end_time, day_end)
            if overlap_start < overlap_end:
                planned_minutes += (overlap_end - overlap_start).total_seconds() / 60

    if total_minutes <= 0:
        return 1.0
    return min(1.0, (occupied_minutes + planned_minutes) / total_minutes)


# ---------------------------------------------------------------------------
# 2. Get at-risk tasks
# ---------------------------------------------------------------------------


async def get_at_risk_tasks(user: str, lookahead_days: int = 7) -> list[dict]:
    """Return all active tasks for *user* with risk scores, sorted by score descending.

    If *user* is "household", fetches all active tasks across all assignees.
    """
    pool = await get_pool()
    today = date.today()
    end_date = today + timedelta(days=lookahead_days)

    async with pool.acquire() as conn:
        if user == "household":
            rows = await conn.fetch(
                """
                SELECT t.id, t.title, t.priority, t.due_at, t.task_duration_min,
                       t.earliest_start, t.latest_end, t.hard_deadline, t.soft_deadline,
                       t.planning_state, t.labels, u.name AS assignee_name
                FROM tasks t
                LEFT JOIN users u ON t.assignee_id = u.id
                WHERE t.status = 'active'
                """
            )
        else:
            rows = await conn.fetch(
                """
                SELECT t.id, t.title, t.priority, t.due_at, t.task_duration_min,
                       t.earliest_start, t.latest_end, t.hard_deadline, t.soft_deadline,
                       t.planning_state, t.labels, u.name AS assignee_name
                FROM tasks t
                LEFT JOIN users u ON t.assignee_id = u.id
                WHERE t.status = 'active' AND u.name = $1
                """,
                user,
            )

    tasks: list[dict] = []
    task_ids: list[str] = []
    for r in rows:
        d = dict(r)
        for k in ("id",):
            d[k] = str(d[k]) if d[k] else None
        tasks.append(d)
        task_ids.append(d.get("id", ""))

    blocked_ids: set[str] = set()
    if task_ids:
        async with pool.acquire() as conn:
            blocker_rows = await conn.fetch(
                """
                SELECT DISTINCT td.child_id
                FROM task_dependencies td
                JOIN tasks t_parent ON t_parent.id = td.parent_id
                WHERE td.child_id = ANY($1::uuid[]) AND t_parent.status = 'active'
                """,
                task_ids,
            )
            for br in blocker_rows:
                blocked_ids.add(str(br["child_id"]))

    for t in tasks:
        t["has_blockers"] = t.get("id") in blocked_ids

    blocks = await load_blocks(pool, user, today, end_date)
    events = await _fetch_calendar_events(today, end_date)

    results = [compute_risk_score(t, blocks, events) for t in tasks]
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# 3. Capacity check
# ---------------------------------------------------------------------------


async def compute_capacity_utilization(
    user: str,
    start_date: date,
    end_date: date,
) -> dict:
    """Return how full the planned schedule is per day and overall.

    Returns dict with per_day, overall, and peak_day.
    """
    pool = await get_pool()
    blocks = await load_blocks(pool, user, start_date, end_date)
    events = await _fetch_calendar_events(start_date, end_date)

    total_minutes = (WORK_DAY_END - WORK_DAY_START) * 60

    per_day: list[dict] = []
    overall_planned = 0
    overall_available = 0
    peak_day: dict | None = None

    current = start_date
    while current <= end_date:
        event_minutes = 0.0
        for ev in events:
            ev_start = _parse_dt(ev.get("start", ""))
            ev_end = _parse_dt(ev.get("end", ""))
            if ev_start and ev_end and ev_start.date() == current:
                day_start = datetime.combine(current, time(WORK_DAY_START, 0, 0), tzinfo=timezone.utc)
                day_end = datetime.combine(current, time(WORK_DAY_END, 0, 0), tzinfo=timezone.utc)
                o_start = max(ev_start, day_start)
                o_end = min(ev_end, day_end)
                if o_start < o_end:
                    event_minutes += (o_end - o_start).total_seconds() / 60

        planned_minutes = 0.0
        for b in blocks:
            if b.planned_date == current and b.start_time and b.end_time:
                day_start = datetime.combine(current, time(WORK_DAY_START, 0, 0), tzinfo=timezone.utc)
                day_end = datetime.combine(current, time(WORK_DAY_END, 0, 0), tzinfo=timezone.utc)
                o_start = max(b.start_time, day_start)
                o_end = min(b.end_time, day_end)
                if o_start < o_end:
                    planned_minutes += (o_end - o_start).total_seconds() / 60

        available = total_minutes - event_minutes
        util = planned_minutes / available if available > 0 else 0.0
        util = min(1.0, max(0.0, util))

        day_entry = {
            "date": current.isoformat(),
            "planned_minutes": int(planned_minutes),
            "available_minutes": int(available),
            "utilization": round(util, 2),
        }
        per_day.append(day_entry)
        overall_planned += int(planned_minutes)
        overall_available += int(available)

        if peak_day is None or day_entry["utilization"] > peak_day["utilization"]:
            peak_day = day_entry

        current += timedelta(days=1)

    return {
        "per_day": per_day,
        "overall": {
            "planned_minutes": overall_planned,
            "available_minutes": overall_available,
            "utilization": round(overall_planned / overall_available, 2) if overall_available > 0 else 0.0,
        },
        "peak_day": peak_day or {"date": "", "utilization": 0.0},
    }


# ---------------------------------------------------------------------------
# 4. Next-best-action
# ---------------------------------------------------------------------------


async def compute_next_best_action(user: str) -> dict:
    """Return the single most impactful actionable item for the user right now."""
    at_risk = await get_at_risk_tasks(user, lookahead_days=7)
    if not at_risk:
        return {"has_next_action": False, "message": "No tasks to recommend."}

    pool = await get_pool()
    today = date.today()

    events = await _fetch_calendar_events(today, today + timedelta(days=2))
    blocks = await load_blocks(pool, user, today, today + timedelta(days=2))

    for task_risk in at_risk:
        task_id = task_risk["task_id"]
        if not task_id:
            continue

        duration_min = task_risk.get("duration_min", 60)

        for day_offset in range(3):
            check_date = today + timedelta(days=day_offset)
            slots = find_available_slots(
                check_date, user, events, blocks,
                min_duration_min=duration_min,
            )
            if slots:
                slot = slots[0]
                return {
                    "has_next_action": True,
                    "task_id": task_id,
                    "title": task_risk["title"],
                    "assignee": task_risk.get("assignee", user),
                    "risk_level": task_risk["level"],
                    "recommended_slot": {
                        "date": check_date.isoformat(),
                        "start": slot.start.strftime("%H:%M"),
                        "end": slot.end.strftime("%H:%M"),
                    },
                    "reasoning": (
                        f"{task_risk['title']} is {task_risk['level']} risk. "
                        f"Next free slot: {check_date.isoformat()} "
                        f"{slot.start.strftime('%H:%M')}-{slot.end.strftime('%H:%M')}."
                    ),
                }

    top = at_risk[0]
    return {
        "has_next_action": True,
        "task_id": top["task_id"],
        "title": top["title"],
        "assignee": top.get("assignee", user),
        "risk_level": top["level"],
        "recommended_slot": None,
        "reasoning": f"{top['title']} is {top['level']} risk but no free slot available in the next 2 days. Make room.",
    }


# ---------------------------------------------------------------------------
# 5. Replan triggers
# ---------------------------------------------------------------------------


async def replan_if_needed(
    user: str,
    affected_date: date,
    reason: str,
    days_forward: int = 7,
) -> bool:
    """Check whether the current plan is still valid after a change; if not, trigger regeneration."""
    pool = await get_pool()
    end_date = affected_date + timedelta(days=days_forward)
    blocks = await load_blocks(pool, user, affected_date, end_date)
    events = await _fetch_calendar_events(affected_date, end_date)

    conflicted_blocks: list[PlannedBlock] = []
    for b in blocks:
        if b.is_occupied or not b.start_time or not b.end_time:
            continue
        for ev in events:
            ev_start = _parse_dt(ev.get("start", ""))
            ev_end = _parse_dt(ev.get("end", ""))
            if ev_start and ev_end and b.start_time < ev_end and b.end_time > ev_start:
                conflicted_blocks.append(b)
                break

    if conflicted_blocks:
        log.info(
            "replan triggered for %s: %d blocks conflicted by %s",
            user, len(conflicted_blocks), reason,
        )
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                asyncio.create_task(
                    generate_plan(user, affected_date, end_date, regenerate=True)
                )
        except RuntimeError:
            log.warning("No running event loop for replan")
        return True
    return False


async def replan_after_task_change(user: str, task_id: str, reason: str) -> bool:
    """Trigger replan when a task's planning metadata may affect the current plan.

    Returns True if replan was triggered.
    """
    pool = await get_pool()
    today = date.today()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT due_at, planning_state FROM tasks WHERE id = $1::uuid",
            task_id,
        )
    if not row:
        return False

    due_at = row["due_at"]
    planning_state = row["planning_state"]

    should_replan = False
    if due_at and isinstance(due_at, datetime) and due_at.date() <= today + timedelta(days=7):
        should_replan = True
    elif planning_state == "scheduled":
        should_replan = True

    if should_replan:
        log.info("replan triggered for %s: task %s changed (%s)", user, task_id, reason)
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                asyncio.create_task(
                    generate_plan(user, today, today + timedelta(days=7), regenerate=True)
                )
        except RuntimeError:
            log.warning("No running event loop for replan_after_task_change")
        return True

    return False
