# Phase 7: Preferences Schema & Identity Migration - Plan

**Status:** Completed

## Goal

Nova's WhatsApp identity resolution and all per-user preference data live in Postgres as the single source of truth, with zero disruption to Ruben & Méral's existing WhatsApp access during cutover.

## Depends On

Phase 6.

## Requirements

ONBOARD-06, ONBOARD-07 (see `.planning/REQUIREMENTS.md`)

## Success Criteria (what must be TRUE)

1. Ruben and Méral's existing WhatsApp numbers keep working identically before and after deploy — no interruption to WA-01/WA-02/WA-03 behavior across the cutover.
2. New preference tables exist in Postgres (verified number, DND window, per-job toggles/times, verification codes) and are seed-migrated with Ruben & Méral's current numbers atomically with the schema change — no separate manual migration step.
3. Nova's WhatsApp sender-to-user resolution reads exclusively from the DB-backed store — no remaining code path in `whatsapp.py` or `scheduler.py` reads `NOVA_WHATSAPP_USERS` directly.

## Approach / Task Breakdown

1. **`services/nova-core/app/db.py` — ONBOARD-06**: Add migrations creating `user_preferences` and `whatsapp_verification_codes` tables and seed-migrate user phone numbers from configuration on startup.
2. **`services/nova-core/app/identity.py` — ONBOARD-07**: Update `user_from_whatsapp` to be an async function querying `user_preferences`. Add `get_all_whatsapp_users()` helper to list all registered users.
3. **`services/nova-core/app/whatsapp.py` — ONBOARD-07**: Await async user resolutions and clean up authorization check.
4. **`services/nova-core/app/scheduler.py` — ONBOARD-07**: Use `await identity.get_all_whatsapp_users()` instead of static dict mapping.
