"""Calendar tool using self-hosted CalDAV (Radicale)."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo
import caldav
from icalendar import Calendar as iCalendar, Event as iEvent

from .base import tool
from ..config import settings
from ..replanning import replan_if_needed

log = logging.getLogger("nova-core.calendar")

_WORK_DAY_START = 8
_WORK_DAY_END = 22

# CalDAV connection timeout in seconds — must match or be less than the
# asyncio.wait_for timeout in _collect_admin_status (currently 5s).
# Prevents the synchronous requests call from blocking the event loop
# indefinitely when the server is unreachable.
_CALDAV_TIMEOUT = 5

# Cached DAVClient + Calendar to avoid a TCP + PROPFIND round-trip on every call.
_calendar_cache: tuple[caldav.DAVClient, caldav.Calendar] | None = None


def _normalize_dt(dt_str: str) -> datetime:
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(settings.nova_timezone))
    return dt


def _get_calendar() -> caldav.Calendar:
    """Create (or return cached) DAVClient + Calendar.

    Uses a module-level cache so that repeated calls within the same process
    reuse the existing TCP connection and avoid a PROPFIND round-trip.

    The underlying requests calls are synchronous — in an async context the
    caller should wrap this in asyncio.to_thread or run_in_executor if the
    event loop must not be blocked.
    """
    global _calendar_cache
    if _calendar_cache is not None:
        return _calendar_cache[1]

    client = caldav.DAVClient(
        url=settings.caldav_url,
        username=settings.caldav_username or None,
        password=settings.caldav_password or None,
        timeout=_CALDAV_TIMEOUT,
    )
    principal = client.principal()
    calendars = principal.calendars()
    if not calendars:
        cal = principal.make_calendar(name="Household", cal_id="household")
    else:
        cal = calendars[0]

    _calendar_cache = (client, cal)
    return cal


def _clear_calendar_cache() -> None:
    """Clear the cached DAVClient + Calendar connection.

    Exposed for testing — call between test cases that use different
    mock configurations to prevent cross-test leakage of the module-level
    _calendar_cache.
    """
    global _calendar_cache
    _calendar_cache = None


@tool(
    name="list_events",
    description="List calendar events in a date range on the shared household calendar.",
    parameters={
        "type": "object",
        "properties": {
            "start": {"type": "string", "description": "ISO date/datetime for range start."},
            "end": {"type": "string", "description": "ISO date/datetime for range end."},
        },
        "required": ["start", "end"],
    },
)
async def list_events(start: str, end: str) -> str:
    try:
        start_dt = _normalize_dt(start)
        end_dt = _normalize_dt(end)
    except ValueError:
        return f"Error: Invalid date format: start='{start}', end='{end}'"

    calendar = _get_calendar()
    # Search for events expanding recurrences
    events = calendar.search(start=start_dt, end=end_dt, event=True, expand=True)

    if not events:
        return f"No events between {start} and {end}."

    lines = []
    for i, event in enumerate(events, 1):
        vobject = event.vobject_instance
        vevent = vobject.vevent
        summary = vevent.summary.value if hasattr(vevent, "summary") else "No Title"
        
        # Get start/end values (can be datetime.date or datetime.datetime)
        dtstart = vevent.dtstart.value if hasattr(vevent, "dtstart") else None
        dtend = vevent.dtend.value if hasattr(vevent, "dtend") else None
        
        dtstart_str = dtstart.isoformat() if dtstart else "unknown"
        dtend_str = dtend.isoformat() if dtend else "unknown"
        location_str = f" @ {vevent.location.value}" if hasattr(vevent, "location") and vevent.location.value else ""
        
        lines.append(f"{i}. {summary}: {dtstart_str} to {dtend_str}{location_str}")

    return f"Events between {start} and {end}:\n" + "\n".join(lines)


@tool(
    name=    "create_event",
    description="Create a calendar event on the shared household calendar.",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "start": {"type": "string", "description": "ISO 8601 start datetime."},
            "end": {"type": "string", "description": "ISO 8601 end datetime."},
            "description": {"type": "string"},
            "rrule": {"type": "string", "description": "iCal RRULE string for recurrence (e.g. FREQ=WEEKLY;BYDAY=MO,WE,FR)"},
            "location": {"type": "string"},
        },
        "required": ["title", "start", "end"],
    },
)
async def create_event(title: str, start: str, end: str, description: str | None = None, rrule: str | None = None, location: str | None = None) -> str:
    try:
        start_dt = _normalize_dt(start)
        end_dt = _normalize_dt(end)
    except ValueError:
        return f"Error: Invalid date format: start='{start}', end='{end}'"

    calendar = _get_calendar()

    # Check for conflicts before creating
    conflicts = await detect_conflicts(start_dt, end_dt)
    if conflicts:
        conflict_summary = "\n".join(
            f"- {c['title']} ({c['start']} to {c['end']})"
            for c in conflicts[:5]
        )
        return (
            f"Warning: The proposed time conflicts with existing events:\n"
            f"{conflict_summary}\n\n"
            f"Event '{title}' was NOT created. Please choose a different time."
        )

    # Construct iCalendar event
    ical = iCalendar()
    ical.add("prodid", "-//Nova Household Assistant//")
    ical.add("version", "2.0")
    
    event = iEvent()
    event.add("summary", title)
    event.add("dtstart", start_dt)
    event.add("dtend", end_dt)
    if description:
        event.add("description", description)
    if rrule:
        try:
            event.add("rrule", rrule)
        except ValueError:
            return f"Error: Invalid RRULE string: '{rrule}'"
    if location:
        event.add("location", location)
    
    ical.add_component(event)
    
    # Save to calendar
    calendar.save_event(ical.to_ical().decode("utf-8"))

    # Phase 44 — trigger replan if the new event conflicts with planned blocks
    try:
        event_start_date = start_dt.date() if isinstance(start_dt, datetime) else start_dt
        if isinstance(event_start_date, date):
            asyncio.create_task(
                replan_if_needed("household", event_start_date, f"new event '{title}'")
            )
    except Exception as replan_err:
        log.warning("replan trigger after create_event failed: %s", replan_err)

    parts = [f"'{title}'"]
    if description:
        parts.append(f"\"{description}\"")
    where = f" @ {location}" if location else ""
    return f"Created event {' '.join(parts)} {start}–{end}{where}."


async def is_user_busy() -> bool:
    """Check if the household calendar has a busy event right now.

    Returns True if the current local time falls within any event's
    start/end range. Reuses the existing CalDAV connection pattern.
    Uses 'household' as default since the calendar is shared.
    """
    import zoneinfo
    from datetime import datetime, timezone, timedelta
    from ..config import settings

    tz = zoneinfo.ZoneInfo(settings.nova_timezone)
    now_local = datetime.now(tz)
    five_min_ago = now_local - timedelta(minutes=5)

    try:
        calendar = _get_calendar()
        events = calendar.search(
            start=five_min_ago,
            end=now_local + timedelta(hours=2),
            event=True, expand=True
        )
        for ev in events:
            try:
                vevent = ev.vobject_instance.vevent
                dtstart = vevent.dtstart.value if hasattr(vevent, "dtstart") else None
                dtend = vevent.dtend.value if hasattr(vevent, "dtend") else None

                if not dtstart or not dtend:
                    continue

                # Normalize to datetime
                if not isinstance(dtstart, datetime):
                    continue
                if not isinstance(dtend, datetime):
                    dtend = datetime.combine(dtend, datetime.max.time(), tzinfo=tz)

                # Check if current time is within event bounds
                if dtstart <= now_local <= dtend:
                    return True
            except Exception:
                continue
    except Exception as e:
        log.warning("is_user_busy calendar query failed: %s", e)
        return False  # Be conservative: if we can't check, don't block
    return False


async def detect_conflicts(start: datetime, end: datetime) -> list[dict]:
    """Detect existing calendar events that conflict with a proposed time slot.

    Returns a list of conflicting events with title, start, end, location.
    Returns empty list on error or no conflicts.
    """
    try:
        calendar = _get_calendar()
        events = calendar.search(start=start, end=end, event=True, expand=True)
    except Exception as e:
        log.warning("detect_conflicts query failed: %s", e)
        return []

    conflicts = []
    for ev in events:
        try:
            vevent = ev.vobject_instance.vevent
            dtstart = vevent.dtstart.value if hasattr(vevent, "dtstart") else None
            dtend = vevent.dtend.value if hasattr(vevent, "dtend") else None
            summary = vevent.summary.value if hasattr(vevent, "summary") else "No Title"
            location = vevent.location.value if hasattr(vevent, "location") and vevent.location.value else ""

            if not dtstart or not dtend:
                continue
            if not isinstance(dtstart, datetime) or not isinstance(dtend, datetime):
                continue

            # Check overlap: A.start < B.end AND A.end > B.start
            uid = str(vevent.uid.value) if hasattr(vevent, "uid") else ""

            if dtstart < end and dtend > start:
                conflicts.append({
                    "title": summary,
                    "start": dtstart.isoformat(),
                    "end": dtend.isoformat(),
                    "location": location,
                    "uid": uid,
                })
        except Exception:
            continue

    return conflicts


# ---------------------------------------------------------------------------
# Plan 46-01: Calendar intelligence tools
# ---------------------------------------------------------------------------


async def _fetch_calendar_events_range(start_dt: datetime, end_dt: datetime) -> list[dict[str, Any]]:
    """Fetch all calendar events in a range and return as dicts with uid."""
    calendar = _get_calendar()
    events = calendar.search(start=start_dt, end=end_dt, event=True, expand=True)
    results: list[dict[str, Any]] = []
    for ev in events:
        try:
            vevent = ev.vobject_instance.vevent
            ds = vevent.dtstart.value if hasattr(vevent, "dtstart") else None
            de = vevent.dtend.value if hasattr(vevent, "dtend") else None
            if ds and de and isinstance(ds, datetime) and isinstance(de, datetime):
                uid = str(vevent.uid.value) if hasattr(vevent, "uid") else ""
                summary = vevent.summary.value if hasattr(vevent, "summary") else "Busy"
                results.append({"start": ds, "end": de, "title": summary, "uid": uid})
        except Exception:
            continue
    return results


def _merge_occupied(occupied: list[dict[str, datetime]]) -> list[dict[str, datetime]]:
    """Merge overlapping or adjacent occupied slots."""
    if not occupied:
        return []
    sorted_slots = sorted(occupied, key=lambda o: o["start"])
    merged: list[dict[str, datetime]] = [dict(sorted_slots[0])]
    for o in sorted_slots[1:]:
        if o["start"] <= merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], o["end"])
        else:
            merged.append(dict(o))
    return merged


@tool(
    name="find_free_slots",
    description="Find free time slots on the shared household calendar within a date range.",
    parameters={
        "type": "object",
        "properties": {
            "start": {"type": "string", "description": "ISO date/datetime for range start."},
            "end": {"type": "string", "description": "ISO date/datetime for range end."},
            "duration_min": {"type": "integer", "description": "Minimum slot duration in minutes.", "default": 30},
        },
        "required": ["start", "end"],
    },
)
async def find_free_slots(start: str, end: str, duration_min: int = 30) -> str:
    try:
        start_dt = _normalize_dt(start)
        end_dt = _normalize_dt(end)
    except ValueError:
        return f"Error: Invalid date format: start='{start}', end='{end}'"

    if duration_min < 1:
        return "Error: duration_min must be at least 1 minute."

    events = await _fetch_calendar_events_range(start_dt, end_dt)
    occupied = [{"start": e["start"], "end": e["end"]} for e in events]
    merged = _merge_occupied(occupied)

    tz = ZoneInfo(settings.nova_timezone)
    cursor_date = start_dt.date() if isinstance(start_dt, datetime) else start_dt
    end_date = end_dt.date() if isinstance(end_dt, datetime) else end_dt

    lines: list[str] = []
    current = cursor_date
    while current <= end_date:
        day_start = datetime.combine(current, datetime.min.time(), tzinfo=tz).replace(hour=_WORK_DAY_START)
        day_end = datetime.combine(current, datetime.min.time(), tzinfo=tz).replace(hour=_WORK_DAY_END)

        cursor = day_start
        day_slots: list[str] = []
        for occ in merged:
            if occ["end"] <= cursor or occ["start"] >= day_end:
                continue
            if occ["start"] > cursor:
                gap_end = min(occ["start"], day_end)
                gap_min = (gap_end - cursor).total_seconds() / 60
                if gap_min >= duration_min:
                    day_slots.append(f"{cursor.strftime('%H:%M')}–{gap_end.strftime('%H:%M')} ({int(gap_min)}min)")
            cursor = max(cursor, occ["end"])
            if cursor >= day_end:
                break

        if cursor < day_end:
            gap_min = (day_end - cursor).total_seconds() / 60
            if gap_min >= duration_min:
                day_slots.append(f"{cursor.strftime('%H:%M')}–{day_end.strftime('%H:%M')} ({int(gap_min)}min)")

        if day_slots:
            lines.append(f"  {current.isoformat()}: {', '.join(day_slots)}")

        current += timedelta(days=1)

    if not lines:
        return f"No free slots of at least {duration_min} minutes between {start} and {end}."

    return f"Free slots (≥{duration_min}min) between {start} and {end}:\n" + "\n".join(lines)


def _find_event_by_title(search_title: str, start_dt: datetime, end_dt: datetime) -> tuple:
    """Find a single calendar event matching *search_title* (case-insensitive).

    Returns (caldav.Event, vevent) tuple.
    Raises ValueError if multiple matches.
    Returns (None, None) if no match.
    """
    calendar = _get_calendar()
    events = calendar.search(start=start_dt, end=end_dt, event=True, expand=False)

    matches: list[tuple] = []
    for ev in events:
        try:
            vevent = ev.vobject_instance.vevent
            summary = vevent.summary.value if hasattr(vevent, "summary") else ""
            if summary.strip().lower() == search_title.strip().lower():
                matches.append((ev, vevent))
        except Exception:
            continue

    if not matches:
        return (None, None)
    if len(matches) > 1:
        raise ValueError(
            f"Multiple events ({len(matches)}) match '{search_title}'. "
            "Please narrow the search range or be more specific."
        )
    return matches[0]


@tool(
    name="edit_event",
    description="Edit an existing calendar event by searching for its title within a date range.",
    parameters={
        "type": "object",
        "properties": {
            "search_title": {"type": "string", "description": "Title of the event to edit (case-insensitive)."},
            "start_range": {"type": "string", "description": "ISO datetime start of search range."},
            "end_range": {"type": "string", "description": "ISO datetime end of search range."},
            "new_title": {"type": "string", "description": "New title for the event."},
            "new_start": {"type": "string", "description": "ISO datetime for new start time."},
            "new_end": {"type": "string", "description": "ISO datetime for new end time."},
            "new_description": {"type": "string", "description": "New description."},
            "new_location": {"type": "string", "description": "New location."},
        },
        "required": ["search_title", "start_range", "end_range"],
    },
)
async def edit_event(
    search_title: str,
    start_range: str,
    end_range: str,
    new_title: str | None = None,
    new_start: str | None = None,
    new_end: str | None = None,
    new_description: str | None = None,
    new_location: str | None = None,
) -> str:
    try:
        start_dt = _normalize_dt(start_range)
        end_dt = _normalize_dt(end_range)
    except ValueError:
        return f"Error: Invalid date format for search range: start='{start_range}', end='{end_range}'"

    try:
        match = _find_event_by_title(search_title, start_dt, end_dt)
    except ValueError as e:
        return f"Error: {e}"
    if match[0] is None:
        return f"Error: No event found with title '{search_title}' in the specified range."

    ev, vevent = match

    new_start_dt = _normalize_dt(new_start) if new_start else None
    new_end_dt = _normalize_dt(new_end) if new_end else None

    if new_start_dt and new_end_dt:
        conflicts = await detect_conflicts(new_start_dt, new_end_dt)
        existing_uid = str(vevent.uid.value) if hasattr(vevent, "uid") else ""
        conflicts = [c for c in conflicts if c.get("uid", "") != existing_uid]
        if conflicts:
            return (
                f"Warning: The proposed new time conflicts with existing events:\n"
                + "\n".join(f"- {c['title']} ({c['start']} to {c['end']})" for c in conflicts[:5])
                + f"\n\nEvent '{search_title}' was NOT updated. Please choose a different time."
            )

    changes: list[str] = []
    if new_title:
        vevent.summary.value = new_title
        changes.append("title")
    if new_start_dt:
        vevent.dtstart.value = new_start_dt
        changes.append("start time")
    if new_end_dt:
        vevent.dtend.value = new_end_dt
        changes.append("end time")
    if new_description is not None:
        if hasattr(vevent, "description"):
            vevent.description.value = new_description
        else:
            desc = vevent.add("description")
            desc.value = new_description
        changes.append("description")
    if new_location is not None:
        if hasattr(vevent, "location"):
            vevent.location.value = new_location
        else:
            loc = vevent.add("location")
            loc.value = new_location
        changes.append("location")

    if not changes:
        return "No changes requested. Provide at least one field to update."

    try:
        ev.save()
    except Exception as e:
        return f"Error: Failed to save event: {e}"

    log.info("Edited event '%s': %s", search_title, ", ".join(changes))
    return f"Updated event '{search_title}': changed {', '.join(changes)}."


@tool(
    name="delete_event",
    description="Delete a calendar event by searching for its title within a date range.",
    parameters={
        "type": "object",
        "properties": {
            "search_title": {"type": "string", "description": "Title of the event to delete (case-insensitive)."},
            "start_range": {"type": "string", "description": "ISO datetime start of search range."},
            "end_range": {"type": "string", "description": "ISO datetime end of search range."},
        },
        "required": ["search_title", "start_range", "end_range"],
    },
)
async def delete_event(search_title: str, start_range: str, end_range: str) -> str:
    try:
        start_dt = _normalize_dt(start_range)
        end_dt = _normalize_dt(end_range)
    except ValueError:
        return f"Error: Invalid date format for search range: start='{start_range}', end='{end_range}'"

    try:
        match = _find_event_by_title(search_title, start_dt, end_dt)
    except ValueError as e:
        return f"Error: {e}"
    if match[0] is None:
        return f"Error: No event found with title '{search_title}' in the specified range."

    ev, vevent = match
    try:
        ev.delete()
    except Exception as e:
        return f"Error: Failed to delete event: {e}"

    log.info("Deleted event '%s'", search_title)
    return f"Deleted event '{search_title}'."


@tool(
    name="reschedule_event",
    description="Reschedule an existing event to a new time. For recurring events, the entire series is rescheduled.",
    parameters={
        "type": "object",
        "properties": {
            "search_title": {"type": "string", "description": "Title of the event to reschedule (case-insensitive)."},
            "start_range": {"type": "string", "description": "ISO datetime start of search range."},
            "end_range": {"type": "string", "description": "ISO datetime end of search range."},
            "new_start": {"type": "string", "description": "ISO datetime for new start time."},
            "new_end": {"type": "string", "description": "ISO datetime for new end time."},
        },
        "required": ["search_title", "start_range", "end_range", "new_start", "new_end"],
    },
)
async def reschedule_event(search_title: str, start_range: str, end_range: str, new_start: str, new_end: str) -> str:
    try:
        start_dt = _normalize_dt(start_range)
        end_dt = _normalize_dt(end_range)
        new_start_dt = _normalize_dt(new_start)
        new_end_dt = _normalize_dt(new_end)
    except ValueError:
        return "Error: Invalid date format."

    try:
        match = _find_event_by_title(search_title, start_dt, end_dt)
    except ValueError as e:
        return f"Error: {e}"
    if match[0] is None:
        return f"Error: No event found with title '{search_title}' in the specified range."

    ev, vevent = match

    is_recurring = hasattr(vevent, "rrule") and vevent.rrule.value is not None

    conflicts = await detect_conflicts(new_start_dt, new_end_dt)
    existing_uid = str(vevent.uid.value) if hasattr(vevent, "uid") else ""
    conflicts = [c for c in conflicts if c.get("uid", "") != existing_uid]
    if conflicts:
        return (
            f"Warning: The proposed new time conflicts with existing events:\n"
            + "\n".join(f"- {c['title']} ({c['start']} to {c['end']})" for c in conflicts[:5])
            + f"\n\nEvent '{search_title}' was NOT rescheduled. Please choose a different time."
        )

    old_summary = vevent.summary.value if hasattr(vevent, "summary") else "?"
    old_start_dt = vevent.dtstart.value if hasattr(vevent, "dtstart") else None
    old_start_str = old_start_dt.isoformat() if isinstance(old_start_dt, datetime) else str(old_start_dt)

    original_description = vevent.description.value if hasattr(vevent, "description") else None
    original_location = vevent.location.value if hasattr(vevent, "location") and vevent.location.value else None
    original_rrule = str(vevent.rrule.value) if is_recurring else None

    try:
        ev.delete()
    except Exception as e:
        return f"Error: Failed to delete old event: {e}"

    calendar = _get_calendar()
    ical = iCalendar()
    ical.add("prodid", "-//Nova Household Assistant//")
    ical.add("version", "2.0")

    new_vevent = iEvent()
    new_vevent.add("summary", old_summary)
    new_vevent.add("dtstart", new_start_dt)
    new_vevent.add("dtend", new_end_dt)
    if original_description:
        new_vevent.add("description", original_description)
    if original_location:
        new_vevent.add("location", original_location)
    if original_rrule:
        new_vevent.add("rrule", original_rrule)

    ical.add_component(new_vevent)

    try:
        calendar.save_event(ical.to_ical().decode("utf-8"))
    except Exception as e:
        return f"Error: Failed to create rescheduled event: {e}"

    recurring_note = (
        f"\nNote: '{old_summary}' is recurring. The entire series has been rescheduled."
        if is_recurring else ""
    )
    log.info("Rescheduled event '%s' from %s to %s–%s", old_summary, old_start_str, new_start, new_end)
    return f"Rescheduled '{old_summary}' from {old_start_str} to {new_start}–{new_end}.{recurring_note}"
