---
phase: 15-per-user-dynamic-scheduling
plan: 01
subsystem: scheduler
tags: [apscheduler, per-user, briefing, scheduling]
requires:
  - phase: 13-per-user-preferences
    provides: user_preferences table with morning/weekly briefing toggles and times
  - phase: 04-channel-adapter
    provides: send_to_user dispatcher for proactive pushes
provides:
  - Audited per-user briefing scheduler as the sole entry point
  - Deprecated legacy WhatsApp-only send_morning_briefing loop
affects: [phase-16-per-user-dnd, phase-33-attention-aware-proactivity]

tech-stack:
  added: []
  patterns:
    - Per-user preference-driven scheduling replaces hardcoded dispatch
    - Legacy entry points delegate to per-user scheduler for backward compat

key-files:
  created: []
  modified:
    - services/nova-core/app/scheduler.py

key-decisions:
  - "send_morning_briefing() preserved as alias delegating to run_briefing_scheduler() for backward compatibility with import in main.py"
  - "No code changes needed to dashboard API — GET /api/preferences and POST /api/preferences/briefings already handle all five briefing fields correctly per user"

patterns-established:
  - "Deprecation pattern: legacy function body replaced with delegation + DEPRECATED comment, no callers broken"

requirements-completed:
  - PREF-01
  - PREF-02
  - PREF-03
  - PREF-04
  - PREF-05
  - PREF-06
  - PREF-07

coverage:
  - id: D1
    description: "Legacy send_morning_briefing() delegates to per-user run_briefing_scheduler() — no independent WhatsApp loop"
    requirement: PREF-04
    verification:
      - kind: unit
        ref: "services/nova-core/app/scheduler.py#L158-L161"
        status: pass
      - kind: other
        ref: "rg get_all_whatsapp_users services/nova-core/app/scheduler.py => 0 matches"
        status: pass
      - kind: other
        ref: "rg send_morning_briefing\( services/nova-core/ --include '*.py' -l => only scheduler.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "run_briefing_scheduler() is the sole registered briefing APScheduler job"
    requirement: PREF-01
    verification:
      - kind: other
        ref: "rg scheduler.add_job.*briefing services/nova-core/app/main.py => only run_briefing_scheduler"
        status: pass
    human_judgment: false
  - id: D3
    description: "GET /api/preferences returns all five briefing fields per user (morning_enabled, morning_time, weekly_enabled, weekly_day, weekly_time)"
    requirement: PREF-05
    verification:
      - kind: unit
        ref: "services/nova-core/app/main.py#L654-L683"
        status: pass
    human_judgment: false
  - id: D4
    description: "POST /api/preferences/briefings accepts and persists all five briefing fields per user via UPSERT"
    requirement: PREF-06
    verification:
      - kind: unit
        ref: "services/nova-core/app/main.py#L862-L904"
        status: pass
    human_judgment: false
  - id: D5
    description: "Dashboard JS reads five briefing fields from DOM and POSTs correct schema"
    requirement: PREF-07
    verification:
      - kind: unit
        ref: "services/nova-core/static/app.js#L652-L687"
        status: pass
    human_judgment: false
  - id: D6
    description: "Preference changes take effect on next 60-second scheduler tick without restart"
    requirement: PREF-03
    verification:
      - kind: unit
        ref: "services/nova-core/app/scheduler.py#L164-L199"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-07-12
status: complete
---

# Phase 15: Per-User Dynamic Scheduling Summary

**Audited per-user briefing scheduler as sole entry point, deprecated legacy WhatsApp-only loop, and verified dashboard API round-trip for per-user scheduling preferences**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-12T16:04:54Z
- **Completed:** 2026-07-12T16:09:00Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- Replaced legacy `send_morning_briefing()` WhatsApp-only loop with delegation to `run_briefing_scheduler()`, eliminating the duplicate code path that bypassed per-user preference checks
- Added deprecation comment above the alias directing developers to use `run_briefing_scheduler()` directly
- Verified `run_briefing_scheduler()` is the sole registered briefing APScheduler job in `main.py` (no `send_morning_briefing` job exists)
- Audited `GET /api/preferences` returns all five briefing fields (`morning_enabled`, `morning_time`, `weekly_enabled`, `weekly_day`, `weekly_time`) with correct defaults
- Audited `POST /api/preferences/briefings` endpoint accepts and persists all five fields via UPSERT
- Verified `app.js` save handler correctly reads DOM, POSTs matching schema, and reloads preferences on save success
- Confirmed preference changes take effect on the next 60-second scheduler tick without restart

## Task Commits

Each task was committed atomically:

1. **Task 1: Deprecate legacy `send_morning_briefing`** — `1d8198d` (fix)
2. **Task 2: Verify per-user briefing API round-trip** — (verification-only, no code changes needed)

**Plan metadata:** (pending metadata commit)

## Files Created/Modified

- `services/nova-core/app/scheduler.py` — `send_morning_briefing()` body replaced with delegation to `run_briefing_scheduler()` + deprecation comment

## Decisions Made

- `send_morning_briefing()` preserved as a backward-compatible alias (delegating to `run_briefing_scheduler()`) rather than removed entirely, since `main.py` imports it and other dependent code may reference it
- No code changes needed for the dashboard API round-trip — the implementation already correctly handles per-user scheduling preferences end-to-end

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Per-user scheduling is correctly wired end-to-end
- Ready for Phase 16 (Per-User Do Not Disturb) which builds on the same `user_preferences` infrastructure
- Ready for Phase 33 (Proactivity That Respects Attention) which refines when proactive pushes fire

---
*Phase: 15-per-user-dynamic-scheduling*
*Completed: 2026-07-12*
