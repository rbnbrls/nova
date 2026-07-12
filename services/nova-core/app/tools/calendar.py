"""Calendar tool using self-hosted CalDAV (Radicale)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import caldav
from icalendar import Calendar as iCalendar, Event as iEvent

from .base import tool
from ..config import settings


def _normalize_dt(dt_str: str) -> datetime:
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(settings.nova_timezone))
    return dt


def _get_calendar() -> caldav.Calendar:
    client = caldav.DAVClient(url=settings.caldav_url)
    principal = client.principal()
    calendars = principal.calendars()
    if not calendars:
        return principal.make_calendar(name="Household", calendar_id="household")
    return calendars[0]


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
        print(f"[ERROR] is_user_busy calendar query failed: {e}")
        return False  # Be conservative: if we can't check, don't block
    return False
