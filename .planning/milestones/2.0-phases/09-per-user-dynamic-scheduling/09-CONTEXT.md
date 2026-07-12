# Phase 9: Per-User Dynamic Scheduling - Context

**Gathered:** 2026-07-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Allows household users to dynamically schedule and configure their morning and weekly briefings directly from the dashboard, replacing static global cron timers with dynamic DB-backed scheduling. Scoped to SCHED-01, SCHED-02, and SCHED-03.

</domain>

<decisions>
## Implementation Decisions

- **Briefing Scheduling Architecture**:
  - Run an interval job check in APScheduler every 1 minute.
  - The job queries `user_preferences` for all users with enabled briefings, matching the current clock minute and weekday against preferred briefing times.
  - This avoids complex scheduling state syncing/rescheduling logic on application restarts or database edits.
- **Weekly Briefings**:
  - Introduce dynamic weekly briefings compiling a 7-day outlook of active tasks and calendar events.
- **API Endpoints**:
  - `POST /api/preferences/briefings`: Updates morning and weekly briefing schedule settings (enabled state, times, days).
- **Dashboard UI**:
  - Add briefing schedule toggle and configuration inputs for Ruben and Méral inside the settings panel.

</decisions>

<code_context>
## Existing Code Insights

- `services/nova-core/app/scheduler.py` has a static `send_morning_briefing()` function.
- `services/nova-core/app/main.py` schedules the briefing statically via a cron trigger at 7:00 AM.
- `user_preferences` table holds columns for morning and weekly briefing flags, times, and day of week.

</code_context>

<specifics>
## Specific Ideas

See `09-PLAN.md`.

</specifics>

<deferred>
## Deferred Ideas

None.
