"""Deterministic auto-scheduler: turn tasks into time-blocked plans.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .config import settings
from .db import get_pool

log = logging.getLogger("nova-core.planning")

WORK_DAY_START = 8
WORK_DAY_END = 22
DEFAULT_DURATION_MIN = 60


@dataclass
class TimeSlot:
    start: datetime
    end: datetime


@dataclass
class PlannedBlock:
    id: str | None = None
    user_id: str | None = None
    task_id: str | None = None
    title: str = ""
    planned_date: date | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    is_occupied: bool = False
    source_event_uid: str | None = None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def compute_score(task: dict) -> float:
    """Derive a 0-1 urgency score from a task dict.

    Keys used: priority, hard_deadline, soft_deadline, due_at.
    """
    priority_weights = {"high": 1.0, "medium": 0.6, "low": 0.3}
    priority = task.get("priority", "medium") or "medium"
    score = priority_weights.get(priority, 0.6)

    now = datetime.now(timezone.utc)

    hard_deadline = task.get("hard_deadline")
    if hard_deadline:
        if isinstance(hard_deadline, datetime):
            hd = hard_deadline
        elif isinstance(hard_deadline, str):
            hd = _parse_dt(hard_deadline)
        else:
            hd = None
        if hd:
            delta = hd - now
            if delta.total_seconds() <= 0:
                score += 0.3
            elif delta < timedelta(days=1):
                score += 0.3
            elif delta < timedelta(days=7):
                score += 0.15

    soft_deadline = task.get("soft_deadline")
    if soft_deadline:
        if isinstance(soft_deadline, datetime):
            sd = soft_deadline
        elif isinstance(soft_deadline, str):
            sd = _parse_dt(soft_deadline)
        else:
            sd = None
        if sd:
            delta = sd - now
            if delta.total_seconds() <= 0:
                score += 0.1
            elif delta < timedelta(days=1):
                score += 0.1

    due_at = task.get("due_at")
    if due_at:
        if isinstance(due_at, datetime):
            da = due_at
        elif isinstance(due_at, str):
            da = _parse_dt(due_at)
        else:
            da = None
        if da:
            delta = da - now
            if delta.total_seconds() <= 0:
                score += 0.1
            elif delta < timedelta(days=1):
                score += 0.1

    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Slot finding
# ---------------------------------------------------------------------------


def _merge_slots(slots: list[TimeSlot]) -> list[TimeSlot]:
    """Merge overlapping or adjacent time slots."""
    if not slots:
        return []
    sorted_slots = sorted(slots, key=lambda s: s.start)
    merged = [sorted_slots[0]]
    for s in sorted_slots[1:]:
        last = merged[-1]
        if s.start <= last.end:
            merged[-1] = TimeSlot(start=last.start, end=max(last.end, s.end))
        else:
            merged.append(s)
    return merged


def find_available_slots(
    day: date,
    user: str,
    calendar_events: list[dict],
    existing_blocks: list[PlannedBlock],
    min_duration_min: int = DEFAULT_DURATION_MIN,
) -> list[TimeSlot]:
    """Return free TimeSlots on *day* for *user* avoiding events and existing blocks.

    Working day is 08:00-22:00 local time.
    """
    tz = ZoneInfo(settings.nova_timezone)
    day_start = datetime.combine(day, time(WORK_DAY_START, 0, 0), tzinfo=tz)
    day_end = datetime.combine(day, time(WORK_DAY_END, 0, 0), tzinfo=tz)

    occupied: list[TimeSlot] = []

    for ev in calendar_events:
        ev_start = _parse_dt(ev.get("start", ""))
        ev_end = _parse_dt(ev.get("end", ""))
        if ev_start and ev_end:
            occupied.append(TimeSlot(start=ev_start, end=ev_end))

    for b in existing_blocks:
        occupied.append(TimeSlot(start=b.start_time, end=b.end_time))

    occupied = _merge_slots(occupied)

    free_slots: list[TimeSlot] = []
    cursor = day_start
    for occ in occupied:
        if occ.end <= cursor:
            continue
        if occ.start > cursor:
            gap_end = min(occ.start, day_end)
            gap = TimeSlot(start=cursor, end=gap_end)
            if (gap.end - gap.start).total_seconds() / 60 >= min_duration_min:
                free_slots.append(gap)
        cursor = max(cursor, occ.end)
        if cursor >= day_end:
            break

    if cursor < day_end:
        gap = TimeSlot(start=cursor, end=day_end)
        if (gap.end - gap.start).total_seconds() / 60 >= min_duration_min:
            free_slots.append(gap)

    return free_slots


# ---------------------------------------------------------------------------
# Schedule builder
# ---------------------------------------------------------------------------


def _parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _get_task_duration_min(task: dict) -> int:
    dur = task.get("task_duration_min")
    if dur is not None and isinstance(dur, (int, float)) and dur > 0:
        return int(dur)
    return DEFAULT_DURATION_MIN


def _get_user_id_for_name(conn: Any, name: str) -> str | None:
    """Resolve a user name to a UUID string. Falls back to 'household'."""
    import asyncpg
    row = conn.fetchrow("SELECT id FROM users WHERE name = $1", name)
    if row:
        return str(row["id"])
    row = conn.fetchrow("SELECT id FROM users WHERE name = 'household'")
    if row:
        return str(row["id"])
    return None


def build_schedule(
    tasks: list[dict],
    calendar_events: list[dict],
    user: str,
    start_date: date,
    end_date: date,
) -> list[PlannedBlock]:
    """Produce a deterministic time-blocked schedule.

    *Score each task, sort by (score DESC, hard_deadline ASC NULLS LAST, title ASC).
    *Iterate through dates placing each task into the earliest fitting slot.
    *Skip if hard constraints (earliest_start, hard_deadline) are violated.
    """
    scored = []
    for t in tasks:
        score = compute_score(t)
        hd = _parse_dt(t.get("hard_deadline"))
        scored.append((score, hd, t.get("title", ""), t))

    scored.sort(key=lambda x: (-x[0], x[1] or datetime.max.replace(tzinfo=timezone.utc), x[2]))

    blocks: list[PlannedBlock] = []
    used_slots: list[PlannedBlock] = []

    for score, hd, title, task in scored:
        placed = False
        current = start_date
        duration_min = _get_task_duration_min(task)
        es = _parse_dt(task.get("earliest_start"))
        hd = _parse_dt(task.get("hard_deadline"))

        while current <= end_date and not placed:
            available = find_available_slots(
                current, user, calendar_events, used_slots, duration_min
            )

            for slot in available:
                task_start = slot.start
                if es and task_start < es:
                    task_start = es
                task_end = task_start + timedelta(minutes=duration_min)

                if task_end > slot.end:
                    continue
                if hd and task_end > hd:
                    continue

                block_title = task.get("title", "Untitled")
                block = PlannedBlock(
                    title=block_title,
                    planned_date=current,
                    start_time=task_start,
                    end_time=task_end,
                )
                blocks.append(block)
                used_slots.append(block)
                placed = True
                break

            current += timedelta(days=1)

    return blocks


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


async def _fetch_calendar_events(start: date, end: date) -> list[dict]:
    """Fetch calendar events in [start, end] via CalDAV.

    Returns list of dicts with 'start', 'end', 'title', 'uid' keys.
    Each event is treated as an occupied block that the planner must avoid.
    """
    try:
        from .tools.calendar import _get_calendar
        cal = await asyncio.to_thread(_get_calendar)
        tz = ZoneInfo(settings.nova_timezone)
        start_dt = datetime.combine(start, time(0, 0), tzinfo=tz)
        end_dt = datetime.combine(end + timedelta(days=1), time(0, 0), tzinfo=tz)

        events = await asyncio.to_thread(
            cal.search, start=start_dt, end=end_dt, event=True, expand=True
        )
    except Exception as e:
        log.warning("_fetch_calendar_events failed: %s", e)
        return []

    result = []
    for ev in events:
        try:
            vevent = ev.vobject_instance.vevent
            dtstart = vevent.dtstart.value if hasattr(vevent, "dtstart") else None
            dtend = vevent.dtend.value if hasattr(vevent, "dtend") else None
            summary = vevent.summary.value if hasattr(vevent, "summary") else "Busy"
            uid = getattr(vevent, "uid", None)
            if uid is not None:
                uid = str(uid.value) if hasattr(uid, "value") else str(uid)

            if dtstart and dtend:
                if not isinstance(dtstart, datetime):
                    continue
                if not isinstance(dtend, datetime):
                    dtend = datetime.combine(dtend, time.max.replace(tzinfo=tz))
                result.append({
                    "start": dtstart.isoformat(),
                    "end": dtend.isoformat(),
                    "title": summary,
                    "uid": uid or "",
                })
        except Exception:
            continue

    return result


async def persist_blocks(pool, blocks: list[PlannedBlock]) -> list[str]:
    """INSERT all blocks into planned_blocks. Returns list of new IDs."""
    if not blocks:
        return []

    async with pool.acquire() as conn:
        ids: list[str] = []
        for b in blocks:
            row_id = await conn.fetchval(
                """
                INSERT INTO planned_blocks
                    (user_id, task_id, title, planned_date, start_time, end_time,
                     is_occupied, source_event_uid)
                VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8)
                RETURNING id
                """,
                b.user_id,
                b.task_id,
                b.title,
                b.planned_date,
                b.start_time,
                b.end_time,
                b.is_occupied,
                b.source_event_uid,
            )
            ids.append(str(row_id))
        return ids


async def load_blocks(
    pool, user_name: str, start_date: date, end_date: date
) -> list[PlannedBlock]:
    """Load planned blocks for *user_name* in the given date range."""
    if user_name == "household":
        user_condition = ""
        params = [start_date, end_date]
    else:
        user_condition = "AND u.name = $3"
        params = [start_date, end_date, user_name]

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT pb.id, pb.user_id, pb.task_id, pb.title,
                   pb.planned_date, pb.start_time, pb.end_time,
                   pb.is_occupied, pb.source_event_uid, pb.created_at
            FROM planned_blocks pb
            JOIN users u ON pb.user_id = u.id
            WHERE pb.planned_date >= $1 AND pb.planned_date <= $2
            {user_condition}
            ORDER BY pb.start_time ASC
            """,
            *params,
        )

    return [
        PlannedBlock(
            id=str(r["id"]),
            user_id=str(r["user_id"]) if r["user_id"] else None,
            task_id=str(r["task_id"]) if r["task_id"] else None,
            title=r["title"],
            planned_date=r["planned_date"],
            start_time=r["start_time"],
            end_time=r["end_time"],
            is_occupied=r["is_occupied"],
            source_event_uid=r["source_event_uid"],
        )
        for r in rows
    ]


async def delete_blocks_in_range(
    pool, user_id: str, start_date: date, end_date: date
) -> int:
    """DELETE planned blocks for *user_id* in date range. Returns count deleted."""
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM planned_blocks
            WHERE user_id = $1::uuid
              AND planned_date >= $2
              AND planned_date <= $3
            """,
            user_id,
            start_date,
            end_date,
        )
    return int(result.split(" ")[-1]) if result else 0


async def _fetch_tasks(pool, user_id: str | None, user_name: str) -> list[dict]:
    """Fetch active tasks with planning metadata.

    If *user_id* is None (household), fetch all active tasks.
    """
    async with pool.acquire() as conn:
        if user_name == "household":
            rows = await conn.fetch(
                """
                SELECT id, title, priority, due_at, task_duration_min,
                       earliest_start, latest_end, hard_deadline, soft_deadline,
                       planning_state, labels
                FROM tasks
                WHERE status = 'active'
                """
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, title, priority, due_at, task_duration_min,
                       earliest_start, latest_end, hard_deadline, soft_deadline,
                       planning_state, labels
                FROM tasks
                WHERE status = 'active' AND assignee_id = $1::uuid
                """,
                user_id,
            )

    result = []
    for r in rows:
        d = dict(r)
        for k in ("id",):
            d[k] = str(d[k]) if d[k] else None
        if d.get("due_at") and isinstance(d["due_at"], datetime):
            d["due_at"] = d["due_at"]
        result.append(d)
    return result


async def generate_plan(
    user: str,
    start_date: date,
    end_date: date,
    regenerate: bool = False,
) -> list[PlannedBlock]:
    """Orchestrator: fetch tasks, calendar events, build schedule, persist.

    If *regenerate* is True, delete existing blocks in range first.
    """
    pool = await get_pool()

    user_id: str | None = None
    if user != "household":
        async with pool.acquire() as conn:
            uid = await conn.fetchval("SELECT id FROM users WHERE name = $1", user)
            if uid:
                user_id = str(uid)

    if regenerate and user_id:
        await delete_blocks_in_range(pool, user_id, start_date, end_date)

    existing_blocks = await load_blocks(pool, user, start_date, end_date)
    tasks = await _fetch_tasks(pool, user_id, user)
    calendar_events = await _fetch_calendar_events(start_date, end_date)

    schedule = build_schedule(tasks, calendar_events, user, start_date, end_date)

    for b in schedule:
        b.user_id = user_id

    if schedule:
        await persist_blocks(pool, schedule)

    return schedule
