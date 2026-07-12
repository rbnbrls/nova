# Phase 7: Preferences Schema & Identity Migration - Context

**Gathered:** 2026-07-12
**Status:** Completed

<domain>
## Phase Boundary

Nova's WhatsApp identity resolution and all per-user preference data live in Postgres as the single source of truth, with zero disruption to Ruben & Méral's existing WhatsApp access during cutover. Scoped strictly to ONBOARD-06 (preferences schema + seed migration) and ONBOARD-07 (identity resolution queries database).

</domain>

<decisions>
## Implementation Decisions

- Define a `user_preferences` table linked to `users(id)` and a `whatsapp_verification_codes` table to hold OTP verification codes (needed in Phase 8).
- Automatically parse `settings.nova_whatsapp_users` during database migrations on startup and seed them into `user_preferences`.
- Make `identity.user_from_whatsapp` asynchronous so it queries the database rather than reading a static mapping.
- Update `whatsapp.py` and `scheduler.py` to use the database-backed async user query function.

</decisions>

<code_context>
## Existing Code Insights

- `app/config.py`: Defined `nova_whatsapp_users: str = ""` which mapped E.164 phone numbers to names.
- `app/identity.py`: Parsed the config string into `_WHATSAPP_USERS` at import time and resolved users synchronously.
- `app/whatsapp.py` and `app/scheduler.py`: Used `identity._WHATSAPP_USERS` directly.

</code_context>

<specifics>
## Specific Ideas

Directly from ROADMAP.md Phase 7 success criteria (ONBOARD-06, ONBOARD-07) — see `07-PLAN.md`.

</specifics>

<deferred>
## Deferred Ideas

None.
