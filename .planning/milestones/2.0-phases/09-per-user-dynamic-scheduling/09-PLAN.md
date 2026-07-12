# Phase 9: Per-User Dynamic Scheduling - Plan

**Status:** Ready

## Goal

Allows household users to dynamically configure and trigger their morning and weekly briefings directly from the dashboard, replacing static global cron timers with dynamic DB-backed scheduling.

## Depends On

Phase 8.

## Requirements

SCHED-01, SCHED-02, SCHED-03 (see `.planning/REQUIREMENTS.md`)

## Success Criteria (what must be TRUE)

1. User can enable/disable their own morning and weekly briefing schedules from the dashboard settings UI.
2. User can configure their preferred briefing times (hour, minute, weekly briefing day of week) on the dashboard settings UI.
3. Background jobs resolve each user's preferences dynamically and send the briefing at their configured time.

## Approach / Task Breakdown

1. **`services/nova-core/app/models.py` — Schema**:
   - Create `BriefingSettingsRequest` to validate schedule updates.
2. **`services/nova-core/app/scheduler.py` — Scheduling Engine**:
   - Implement `send_morning_briefing_for_user()` and `send_weekly_briefing_for_user()`.
   - Implement `run_briefing_scheduler()` checking database records every 1 minute.
3. **`services/nova-core/app/main.py` — Web API & Lifecycle**:
   - Register `POST /api/preferences/briefings` to update settings in the DB.
   - Replace static `send_morning_briefing` cron trigger with interval job checking briefings every 1 minute.
4. **`services/nova-core/static/index.html` & `app.js` — Frontend UI**:
   - Expand the Preferences panel with Morning Briefing and Weekly Briefing settings (toggles, time picker, day-of-week picker).
   - Display and update briefing configs dynamically.
5. **`services/nova-core/tests/test_scheduler.py` — Verification**:
   - Adapt/add tests to cover dynamic job triggers and briefing compilation.
