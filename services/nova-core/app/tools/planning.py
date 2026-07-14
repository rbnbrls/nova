"""Planning tool — generate time-blocked schedules for the household.
"""
from __future__ import annotations

from datetime import date, datetime

from .base import tool
from .. import planning


@tool(
    name="generate_plan",
    description="Generate a time-blocked daily or weekly plan for a household member, considering deadlines, task durations, priorities, and existing calendar events.",
    parameters={
        "type": "object",
        "properties": {
            "user": {
                "type": "string",
                "enum": ["Ruben", "Meral", "household"],
                "description": "Who to plan for. Defaults to the requester.",
            },
            "start_date": {
                "type": "string",
                "description": "ISO date for plan start, e.g. 2026-07-15. Defaults to today.",
            },
            "end_date": {
                "type": "string",
                "description": "ISO date for plan end, e.g. 2026-07-21. Defaults to start_date (single day).",
            },
            "regenerate": {
                "type": "boolean",
                "description": "If true, drop existing blocks and recompute. Default false (preserves existing blocks, only schedules unscheduled tasks).",
            },
        },
    },
)
async def generate_plan(
    user: str,
    start_date: str | None = None,
    end_date: str | None = None,
    regenerate: bool = False,
) -> str:
    try:
        today = date.today()
        sd = datetime.fromisoformat(start_date).date() if start_date else today
        ed = datetime.fromisoformat(end_date).date() if end_date else sd
    except (ValueError, TypeError) as e:
        return f"Error: Invalid date format: {e}"

    try:
        blocks = await planning.generate_plan(user, sd, ed, regenerate)
    except Exception as e:
        return f"Error generating plan: {e}"

    if not blocks:
        return f"No tasks could be scheduled for {user} between {sd} and {ed}. Try adding some tasks first or adjusting the date range."

    lines = [f"Generated plan for {user} ({sd} to {ed}):\n"]
    by_date: dict[date, list[planning.PlannedBlock]] = {}
    for b in blocks:
        bd = b.planned_date or b.start_time.date()
        by_date.setdefault(bd, []).append(b)

    for d in sorted(by_date.keys()):
        lines.append(f"  {d.isoformat()}:")
        for b in sorted(by_date[d], key=lambda x: x.start_time or datetime.min):
            ts = b.start_time.strftime("%H:%M") if b.start_time else "??:??"
            te = b.end_time.strftime("%H:%M") if b.end_time else "??:??"
            lines.append(f"    {ts}-{te}  {b.title}")
        lines.append("")

    return "\n".join(lines)
