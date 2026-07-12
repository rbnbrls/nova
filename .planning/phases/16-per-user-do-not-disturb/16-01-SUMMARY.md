---
phase: 16-per-user-do-not-disturb
plan: 01
subsystem: channels
tags: [dnd, dispatcher, whatsapp, telegram, channels]
requires:
  - phase: 15-01
    provides: user-level DND settings (dnd_enabled, dnd_start, dnd_end in user_preferences)
provides:
  - Centralized DND enforcement in dispatcher for all proactive outbound sends
  - Correct channel-specific queuing for suppressed messages
affects: [scheduler, outbound channels, dashboard]
tech-stack:
  added: []
  patterns:
    - Single DND gate at dispatcher level instead of per-channel enforcement
    - Queuing suppressed messages with correct channel for later replay
key-files:
  created: []
  modified:
    - services/nova-core/app/channels/dispatcher.py
    - services/nova-core/app/channels/whatsapp.py
    - services/nova-core/app/channels/telegram.py
key-decisions:
  - "DND enforcement centralized to dispatcher.send_to_user() — all proactive sends gated once"
  - "Telegram _send_to_chat_id retains defense-in-depth DND check for legacy call paths"
  - "Suppressed messages queued with correct channel identifier for correct replay by process_queued_notifications"
  - "Queue INSERT uses whatsapp_number column for channel_id (existing schema) and channel column for routing"
patterns-established:
  - "Dispatcher-level DND gate: resolve channel, check DND, queue if active, otherwise route to adapter"
  - "Channel adapters remove redundant DND checks but may retain defense-in-depth for direct call paths"
requirements-completed:
  - DND-01
  - DND-02
  - DND-03
  - DND-04
coverage:
  - id: D1
    description: "Dispatcher checks is_user_in_dnd() before routing proactive sends and queues suppressed messages with correct channel"
    requirement: DND-01
    verification:
      - kind: unit
        ref: "services/nova-core/app/channels/dispatcher.py#send_to_user DND gate"
        status: pass
    human_judgment: false
  - id: D2
    description: "WhatsApp adapter no longer has independent DND enforcement (handled upstream)"
    requirement: DND-02
    verification:
      - kind: unit
        ref: "services/nova-core/app/channels/whatsapp.py#_send_to_number DND check removed"
        status: pass
    human_judgment: false
  - id: D3
    description: "Telegram adapter queues (not drops) proactive messages during DND with channel='telegram'"
    requirement: DND-03
    verification:
      - kind: unit
        ref: "services/nova-core/app/channels/telegram.py#_send_to_chat_id DND queues"
        status: pass
    human_judgment: false
  - id: D4
    description: "DND-suppressed messages are stored with correct channel for later replay by process_queued_notifications"
    requirement: DND-04
    verification:
      - kind: unit
        ref: "services/nova-core/app/channels/dispatcher.py queued_notifications INSERT"
        status: pass
    human_judgment: false
duration: 2m
completed: 2026-07-12
status: complete
---

# Phase 16: Per-User Do Not Disturb Summary

**Centralized DND enforcement in dispatcher with correct channel queuing for suppressed messages**

## Performance

- **Duration:** 2m
- **Started:** 2026-07-12T16:04:20Z
- **Completed:** 2026-07-12T16:06:14Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments

- Added DND check to `dispatcher.send_to_user()` — gates all proactive outbound sends before routing to channel adapter
- Suppressed messages are queued with the correct channel (`'telegram'` or `'whatsapp'`) for replay by `process_queued_notifications`
- Removed redundant DND enforcement from WhatsApp adapter `_send_to_number()` — now handled upstream in the dispatcher
- Changed Telegram adapter `_send_to_chat_id()` from silently dropping proactive messages during DND to queuing them with `channel='telegram'`
- Telegram `_send_to_chat_id` retains a defense-in-depth DND check for legacy call paths that bypass the dispatcher

## Task Commits

Each task was committed atomically:

1. **Task 1: Move DND enforcement to the dispatcher and queue suppressed messages with correct channel** — `b005650` (feat)

**Plan metadata:** (final commit pending)

## Files Created/Modified

- `services/nova-core/app/channels/dispatcher.py` — Added DND gate in `send_to_user()` after resolving `last_channel` but before routing to adapter; queues suppressed messages with correct channel
- `services/nova-core/app/channels/whatsapp.py` — Removed redundant DND enforcement block from `_send_to_number()`; replaced with comment noting DND is handled upstream
- `services/nova-core/app/channels/telegram.py` — Changed `_send_to_chat_id()` DND behavior from silent-drop to queuing with `channel='telegram'`

## Decisions Made

- **Centralized DND in dispatcher:** Every proactive outbound send now goes through a single DND gate at `send_to_user()`, ensuring consistent per-user quiet-hours enforcement across all channels
- **Defense-in-depth retained for Telegram:** `_send_to_chat_id()` still checks DND because it can be called directly by `send_telegram_message()` from legacy code paths — will be removed once all call sites migrate to the dispatcher
- **Channel-specific queuing:** The `channel` column in `queued_notifications` stores the resolved `last_channel` so `process_queued_notifications()` in scheduler correctly routes replayed messages to the right adapter
- **No changes to identity.py:** `is_user_in_dnd()` is correct and unchanged; `process_queued_notifications()` in scheduler.py already reads the `channel` column

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- DND enforcement is now centralized in the dispatcher; channel adapters no longer manage DND independently
- Future phases can add new channels without duplicating DND logic
- Existing Telegram call sites that bypass the dispatcher still get DND protection via the defense-in-depth check

## Self-Check: PASSED

- [x] dispatcher.py exists
- [x] whatsapp.py exists
- [x] telegram.py exists
- [x] Commit `b005650` exists
- [x] 16-01-SUMMARY.md exists

---

*Phase: 16-per-user-do-not-disturb*
*Completed: 2026-07-12*
