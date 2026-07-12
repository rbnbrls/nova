---
phase: 33
plan: 01
subsystem: nova-core (scheduler, dispatcher, calendar, dashboard)
tags:
  - proactivity
  - calendar-awareness
  - deadline-escalation
  - dashboard
requires:
  - 15-01 (per-user scheduling)
  - 16-01 (per-user DND)
  - 12-01 (read-only dashboard)
  - 05-01 (calendar integration)
provides:
  - calendar-busy gate for proactive sends
  - 3-stage deadline escalation
  - dashboard overdue task flag
affects:
  - services/nova-core/app/scheduler.py
  - services/nova-core/app/tools/calendar.py
  - services/nova-core/app/channels/dispatcher.py
  - services/nova-core/app/main.py
  - services/nova-core/static/app.js
  - services/nova-core/static/style.css
tech-stack:
  added: []
  patterns:
    - Lazy calendar check before proactive message sends
    - Event-bound-based meeting detection using CalDAV search
    - Risk-based escalation (gentle → firm → overdue)
key-files:
  created: []
  modified:
    - services/nova-core/app/tools/calendar.py
    - services/nova-core/app/channels/dispatcher.py
    - services/nova-core/app/scheduler.py
    - services/nova-core/app/main.py
    - services/nova-core/static/app.js
    - services/nova-core/static/style.css
decisions:
  - is_user_busy() is async def even though underlying CalDAV client is sync — future-proof for async migration
  - Calendar unavailable → pass (fail-open) rather than block messages
  - Meetings are not queued — scheduler retries in 60 seconds due to transient nature
  - 48h threshold chosen for dashboard overdue flag to match escalation stage boundary
metrics:
  duration: ~6 minutes
  completed_date: 2026-07-12
status: complete
---

# Phase 33 Plan 01: Proactivity That Respects Attention — Summary

Added two intelligence layers to proactive delivery: calendar-busy detection (don't interrupt meetings) and multi-stage deadline escalation (gentle → firm → overdue), plus a dashboard overdue flag.

## Tasks Completed

### Task 1: `is_user_busy()` calendar gate + dispatcher wiring

- **Added `is_user_busy()`** in `app/tools/calendar.py` — checks shared CalDAV calendar for events covering the current local time window (looks 5 min back, 2 hours forward)
- Handles all-day events (skips date-only `dtstart`), multi-day events (expanded by CalDAV), and calendar errors (returns `False` — fail-open)
- **Wired calendar-awareness gate** in `dispatcher.py` `send_to_user()` — after the DND check but before channel routing, suppresses proactive sends during meetings
- Gate only applies to `proactive=True` sends; inbound chat and non-proactive sends are never affected
- Meetings are not queued (unlike DND) — scheduler naturally retries in 60 seconds

### Task 2: Deadline escalation + dashboard overdue flag

- **Replaced `check_overdue_tasks()`** in `app/scheduler.py` with 3-stage escalation:
  - **Gentle reminder**: due today within next 24h — `"'Title' is due today at HH:MM."`
  - **Firm reminder**: 0-48h overdue — `"'Title' was due today/yesterday. Please complete it."`
  - **Overdue flag**: 48h+ overdue — `"⚠ Overdue (Nd): 'Title'. Please complete as soon as possible."`
- **Added `overdue` boolean** to `/dashboard/tasks` endpoint in `main.py` — `True` when task due_at is 48+ hours in the past
- **Dashboard OVERDUE badge** in `app.js` `updateTasks()` — renders a `badge-warning` OVERDUE label for tasks with `overdue=true`, plus `overdue-flag` class for red left-border highlight
- **CSS styles** added for `.todo-item.overdue-flag` and `.badge-warning` in `style.css`

## Threat Mitigation

| Threat | Disposition | Status |
|--------|-------------|--------|
| T-33-01: Calendar unavailable causes suppression | Mitigate — `is_user_busy()` catches all exceptions, returns False | ✅ Implemented |
| T-33-02: Calendar event info used for scheduling | Accept — shared household data, already accessible via chat | ✅ Accepted |
| T-33-03: Escalation spam from rapidly recurring tasks | Mitigate — `check_overdue_tasks()` runs hourly via APScheduler | ✅ Implemented |
| T-33-SC: No new packages | Mitigate — caldav/httpx/apscheduler already in project | ✅ No new deps |

## Deviations from Plan

**None** — plan executed exactly as written. The Phase 34 parallel execution wave already committed the `scheduler.py` and `main.py` changes (identical content), so only `app.js` and `style.css` needed a separate Task 2 commit.

## Stub Tracking

No stubs found — all changes are production-ready:
- `is_user_busy()` is fully wired with real CalDAV queries
- `check_overdue_tasks()` has all 3 escalation stages with proper datetime math
- Dashboard `overdue` field is computed from actual `due_at` timestamps

## Threat Flags

None — no new security-relevant surface introduced beyond the planned threat model.
