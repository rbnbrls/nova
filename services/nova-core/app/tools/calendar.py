"""Calendar tool (self-hosted CalDAV) — STUB.

Phase 5 wires these to the CalDAV server (HA local calendar or Radicale/Nextcloud).
"""
from __future__ import annotations

from .base import tool


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
    # TODO(Phase 5): query CalDAV for events between start and end.
    return f"[stub] No events between {start} and {end}."


@tool(
    name="create_event",
    description="Create a calendar event on the shared household calendar.",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "start": {"type": "string", "description": "ISO 8601 start datetime."},
            "end": {"type": "string", "description": "ISO 8601 end datetime."},
            "location": {"type": "string"},
        },
        "required": ["title", "start", "end"],
    },
)
async def create_event(title: str, start: str, end: str, location: str | None = None) -> str:
    # TODO(Phase 5): create a VEVENT via CalDAV.
    where = f" @ {location}" if location else ""
    return f"[stub] Created event '{title}' {start}–{end}{where}."
