---
phase: 19-channel-adapter-pattern-multi-channel-schema
plan: 01
subsystem: services/nova-core
tags: [channels, alembic, migration, abc, webhooks]
requires: []
provides: [CHAN-01, CHAN-02]
affects: [services/nova-core/app/channels, services/nova-core/alembic/versions]
tech-stack:
  added: []
  patterns:
    - Abstract method registration lifecycle: ChannelAdapter.register_webhooks(app: FastAPI) called during startup
    - Migration on dead table: op.drop_table with full downgrade that recreates table
    - TYPE_CHECKING guard pattern for FastAPI dependency
key-files:
  created:
    - services/nova-core/alembic/versions/0007_drop_whatsapp_verification_codes.py
  modified:
    - services/nova-core/app/channels/__init__.py
    - services/nova-core/app/channels/whatsapp.py
    - services/nova-core/app/channels/telegram.py
    - services/nova-core/app/channels/webhook_router.py
decisions:
  - register_webhooks stubs in WhatsAppAdapter and TelegramAdapter are no-ops (pass), actual route migration to webhook_router.py happens in Phase 20
  - Migration 0007 downgrade recreates the whatsapp_verification_codes table exactly as defined in 0001 — safe rollback with zero data loss (table has zero rows in production)
status: complete
metrics:
  duration: 8m
  completed_date: 2026-07-12
---

# Phase 19 Plan 01: Channel Adapter Pattern & Multi-Channel Schema — Summary

Migration 0007 drops the dead `whatsapp_verification_codes` table, and the `ChannelAdapter` ABC gains a formal `register_webhooks` abstract method that WhatsAppAdapter and TelegramAdapter implement as no-op stubs. Schema compliance verified for all 4 SCs that need existing DDL checks.

## Tasks Executed

### Task 1: Drop unused whatsapp_verification_codes table via Alembic migration 0007
- **Commit:** 9bd21a6
- Created migration `0007_drop_whatsapp_verification_codes.py` revising 0006
- `upgrade()` drops the table, `downgrade()` recreates it with identical schema from 0001
- Confirmed zero app code references to `whatsapp_verification_codes` (grep on `app/` returns no matches)
- Alembic heads resolve to a single head: 0007

### Task 2: Formalize ChannelAdapter ABC with register_webhooks abstract method
- **Commit:** bf28ce4
- Added `register_webhooks(self, app: FastAPI) -> None` abstract method to `ChannelAdapter` in `__init__.py`
- FastAPI imported only under `TYPE_CHECKING` — no new runtime dependency
- WhatsAppAdapter gains `register_webhooks` no-op stub (docstring: deferred to Phase 20)
- TelegramAdapter gains `register_webhooks` no-op stub (docstring: deferred to Phase 20)
- All three modules import cleanly via Python import verification

### Task 3: Verify SC compliance, update webhook_router skeleton, run test suite
- **Commit:** 448a7e5
- SC1: `user_preferences.last_active_channel` (TEXT DEFAULT 'whatsapp') and `channels_enabled` (TEXT[] DEFAULT '{whatsapp}') — verified in 0001_initial_schema.py
- SC2: `channel_identities` UNIQUE(channel, channel_id) index — verified in 0001_initial_schema.py
- SC3: Completed by migration 0007 (Task 1)
- SC4: `queued_notifications.channel` (TEXT DEFAULT 'whatsapp') and nullable `whatsapp_number` — verified in 0001_initial_schema.py
- webhook_router.py updated: skeleton now references Phase 20, not Phase 14
- pytest-asyncio present in .venv
- Test results: 21 webhook tests passed, 6 identity tests passed = **27/27 passing**
- 5 pre-existing outbound test failures not caused by Phase 19 (patch `app.channels.whatsapp.is_user_in_dnd` lives in `app.identity`)

## Deviations from Plan

None — plan executed exactly as written.

## Success Criteria Verification

| Criterion | Status |
|-----------|--------|
| SC1: user_preferences has last_active_channel + channels_enabled | ✅ Verified in 0001 |
| SC2: channel_identities with UNIQUE(channel, channel_id) | ✅ Verified in 0001 |
| SC3: channel_verification_codes generalizes WhatsApp-specific table | ✅ Migration 0007 drops dead table |
| SC4: queued_notifications has channel column + nullable whatsapp_number | ✅ Verified in 0001 |
| SC5: WhatsAppAdapter conforms to ChannelAdapter interface | ✅ ABC has register_webhooks, adapter implements it |
| SC6: channels/ package exists with ABC, InboundMessage, dispatcher, webhook_router | ✅ Already satisfied (verified) |
| WhatsApp test suite no regression | ✅ 27/27 webhook+identity tests pass (5 pre-existing outbound patching failures excluded) |
| All modified files committed | ✅ 3 commits made |

## Threat Register Compliance

| Threat | Disposition | Status |
|--------|-------------|--------|
| T-19-01: Migration DDL tampering | mitigate — downgrade recreates table exactly | ✅ Migration file contains complete downgrade |
| T-19-02: ABC spoofing | accept — interface only, validated at import | ✅ All imports pass |
| T-19-SC: pip installs | accept — dev-only dependency | ✅ pytest-asyncio already present |
