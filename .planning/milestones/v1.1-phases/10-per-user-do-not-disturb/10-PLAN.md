# Phase 10: Per-User Do Not Disturb - Plan

**Status:** Ready

## Goal

Enables dynamic, per-user Do Not Disturb (DND) periods configured via the dashboard. Any proactively scheduled briefings or background alerts triggered during a user's active DND window are deferred into a database queue and delivered immediately when the window ends (or DND is disabled).

## Depends On

Phase 9.

## Requirements

DND-01, DND-02, DND-03 (see `.planning/REQUIREMENTS.md`)

## Success Criteria (what must be TRUE)

1. User can configure their daily Do Not Disturb time window (start/end) and toggle DND state from the settings UI.
2. Scheduled briefings or background alerts destined for them during their active DND window are queued in the database rather than sent immediately.
3. Chatbot responses triggered by direct user interactions are sent immediately even during active DND hours.
4. Queued briefings/alerts are automatically delivered when the user's active DND window ends (or when they disable DND).

## Approach / Task Breakdown

1. **`services/nova-core/app/db.py` — Schema**:
   - Add `queued_notifications` migration to `run_migrations()`.
2. **`services/nova-core/app/models.py` — Schema**:
   - Add `DNDSettingsRequest(BaseModel)` to validate updates.
3. **`services/nova-core/app/identity.py` — Logic**:
   - Implement `is_user_in_dnd(user_name)` handling overnight windows.
4. **`services/nova-core/app/whatsapp.py` — Queuing Engine**:
   - Add `proactive: bool = False` to `send_whatsapp_message()`. If DND is active and `proactive` is True, insert into `queued_notifications` instead of sending.
5. **`services/nova-core/app/scheduler.py` — scheduler checks**:
   - Update scheduled briefings, task overdue alerts, and email alerts to call `send_whatsapp_message` with `proactive=True`.
   - Implement `process_queued_notifications()` running every 1 minute.
6. **`services/nova-core/app/main.py` — Endpoints & lifespans**:
   - Add `POST /api/preferences/dnd`.
   - Register `process_queued_notifications` to run every 1 minute.
7. **`services/nova-core/static/index.html` & `app.js` — Frontend settings**:
   - Add DND toggles and time ranges to settings card. Bind values and saving triggers.
8. **`services/nova-core/tests/test_dnd.py` — Verification**:
   - Add tests to verify queuing during DND, immediate chatbot replies during DND, and delivery flushes.
