# Phase 10 Summary: Per-User Do Not Disturb

> Written 2026-07-12, documenting the implementation of Phase 10.

## Shipped

We implemented changes to allow daily dynamic per-user Do Not Disturb (DND) periods and message queuing:
- `services/nova-core/app/db.py` — Added migration for `queued_notifications` table in the database.
- `services/nova-core/app/models.py` — Created `DNDSettingsRequest` model schema.
- `services/nova-core/app/identity.py` — Implemented `is_user_in_dnd()` helper supporting overnight window checks (e.g. 22:00 to 07:00).
- `services/nova-core/app/whatsapp.py` — Added `proactive` argument to `send_whatsapp_message()`. If DND is active and `proactive` is True, the message is queued in the database.
- `services/nova-core/app/scheduler.py` — Tagged all scheduler briefs and email/task alerts as proactive, and implemented the 1-minute interval `process_queued_notifications()` flusher.
- `services/nova-core/app/main.py` — Added `POST /api/preferences/dnd` endpoint to save settings and registered `process_queued_notifications` task in lifespans.
- `services/nova-core/static/index.html` — Added DND checkbox toggle, start and end timepicker inputs.
- `services/nova-core/static/app.js` — Prefilled and saved DND configurations.
- `services/nova-core/static/style.css` — Configured a beautiful 3-column settings panel structure on wide screens.

## Mapping to Success Criteria

1. **Dashboard toggle DND schedules** — PASS. Handled via inputs in settings panel card.
2. **Alerts queued during DND** — PASS. Proactive messages are correctly inserted into `queued_notifications` during DND. Verified in `test_dnd.py::test_proactive_queued_during_dnd`.
3. **Chatbot replies bypass DND** — PASS. Non-proactive messages bypass checks and are delivered immediately. Verified in `test_dnd.py::test_proactive_queued_during_dnd`.
4. **Queue flushed when DND ends** — PASS. Periodically processed and sent. Verified in `test_dnd.py::test_process_queued_notifications_flush`.
