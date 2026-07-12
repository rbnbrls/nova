# Phase 10: Per-User Do Not Disturb - Context

**Gathered:** 2026-07-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Enables dynamic, per-user Do Not Disturb (DND) periods configured via the dashboard. Any proactively scheduled briefings or background alerts triggered during a user's active DND window are deferred into a database queue and delivered immediately when the window ends (or DND is disabled). User-initiated interactions bypass DND and receive instant bot responses. Scoped to DND-01, DND-02, and DND-03.

</domain>

<decisions>
## Implementation Decisions

- **DND Check Logic**:
  - Implement a helper `is_user_in_dnd()` in `identity.py` that checks the user's local time window.
  - Supports overnight intervals (e.g. 22:00 to 07:00) by checking if current time is >= start OR <= end when start > end.
- **Queuing Engine**:
  - Introduce the `queued_notifications` table in Postgres.
  - Add `proactive: bool = False` flag to `send_whatsapp_message()`. If `proactive=True` and the user is in DND, queue the message and do not send it.
  - Direct responses to user messages (e.g., LLM replies from webhooks) keep `proactive=False` and are sent immediately.
- **Queue Polling**:
  - Schedule a background processing task `process_queued_notifications` running every 1 minute to check for and flush queued messages for users whose DND window has ended or DND was disabled.
- **API Endpoints**:
  - `POST /api/preferences/dnd` - Saves DND state and time windows.

</decisions>

<code_context>
## Existing Code Insights

- `user_preferences` table contains `dnd_enabled`, `dnd_start`, and `dnd_end` columns.
- `app/whatsapp.py` has `send_whatsapp_message()` which handles outbound E.164 sends.

</code_context>

<specifics>
## Specific Ideas

See `10-PLAN.md`.

</specifics>

<deferred>
## Deferred Ideas

None.
