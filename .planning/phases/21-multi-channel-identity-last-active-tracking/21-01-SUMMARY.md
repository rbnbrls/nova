---
phase: 21-multi-channel-identity-last-active-tracking
plan: 01
subsystem: api
tags: [asyncpg, alembic, identity, channel, whatasapp, telegram]
requires:
  - phase: 04-whatsapp-integration
    provides: Whatsapp channel handler with last_inbound_at updates
  - phase: 09-telegram-integration
    provides: Telegram channel handler with last_inbound_at updates
  - phase: 20-consolidated-preferences-and-linking
    provides: channel_identities table, OTP linking flow
provides:
  - Atomic last-active tracking (last_inbound_at + last_active_channel in same transaction) for WhatsApp and Telegram
  - channels/identity.py resolve() returns User dataclass (or HOUSEHOLD) instead of str|None
  - WhatsApp numbers mirrored into channel_identities for unified identity resolution
  - Migration to backfill existing WhatsApp numbers into channel_identities
  - OTP verify endpoint writes to both user_preferences and channel_identities atomically
affects: [phase-21-followup, phase-32-household-coordination]
tech-stack:
  added: []
  patterns:
    - "Multi-statement DB operations wrapped in explicit conn.transaction() for atomicity"
    - "channels/identity.py resolve() returns User dataclass matching identity.py conventions"
key-files:
  created:
    - services/nova-core/alembic/versions/0009_backfill_channel_identities_whatsapp.py
  modified:
    - services/nova-core/app/channels/whatsapp.py
    - services/nova-core/app/channels/telegram.py
    - services/nova-core/app/channels/identity.py
    - services/nova-core/app/main.py
    - services/nova-core/app/db.py
    - services/nova-core/tests/test_identity.py
    - services/nova-core/tests/test_webhooks.py
    - services/nova-core/tests/test_telegram.py
key-decisions:
  - "Used migration 0009 instead of 0008 (0008 already exists for grocery_items table)"
  - "Also wrapped Telegram OTP linking path in conn.transaction() for consistency (matching WhatsApp)"
patterns-established:
  - "Atomic DB updates: wrap multi-statement writes in async with conn.transaction()"
  - "Identity resolution: channels/identity.py resolve() returns User | HOUSEHOLD, matching identity.py conventions"
requirements-completed: [CHAN-03]
duration: 18min
completed: 2026-07-12
status: complete
---

# Phase 21 Plan 01: Multi-Channel Identity & Last-Active Tracking Summary

**Atomic last-active tracking (transaction-wrapped updates) in both WhatsApp and Telegram handlers, plus WhatsApp identity backfill into channel_identities with unified resolve() returning User dataclass**

## Performance

- **Duration:** 18 min
- **Started:** 2026-07-12T15:42:43Z
- **Completed:** 2026-07-12T16:00:43Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- Wrapped WhatsApp last_inbound_at + last_active_channel UPDATEs in explicit `async with conn.transaction()` — crash between the two no longer leaves stale state (D-01)
- Wrapped Telegram last_inbound_at + last_active_channel UPDATEs in explicit `async with conn.transaction()` — same atomicity guarantee (D-01)
- Aligned `channels/identity.py:resolve()` return type from `str | None` to `User` dataclass per identity.py conventions (D-03)
- Added `channel_identities` INSERT in OTP verify path for WhatsApp linking (main.py) — new WhatsApp links write to both user_preferences and channel_identities atomically (D-02)
- Added `channel_identities` INSERT in startup seed (db.py) — WhatsApp numbers from config are mirrored into channel_identities during init (D-02)
- Created Alembic migration `0009_backfill_channel_identities_whatsapp.py` to backfill existing WhatsApp numbers into channel_identities (D-02)
- All 56 existing + new tests pass with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Wrap WhatsApp and Telegram last-active UPDATEs in explicit transactions** — `ca72b4d` (feat)
2. **Task 2: Backfill WhatsApp into channel_identities + align resolve() + wire OTP + tests** — `2dd7132` (feat)

## Files Created/Modified

- `services/nova-core/app/channels/whatsapp.py` — Added `async with conn.transaction()` wrapping last_inbound_at + last_active_channel UPDATEs (line 345)
- `services/nova-core/app/channels/telegram.py` — Added `async with conn.transaction()` wrapping last_inbound_at + last_active_channel UPDATEs (line 272)
- `services/nova-core/app/channels/identity.py` — `resolve()` now returns `User` (or `HOUSEHOLD`), imported from `..identity`
- `services/nova-core/app/main.py` — `verify_code` WhatsApp path now writes to `channel_identities` and wraps all three statements in `conn.transaction()`
- `services/nova-core/app/db.py` — Startup seed now also inserts WhatsApp numbers into `channel_identities`
- `services/nova-core/alembic/versions/0009_backfill_channel_identities_whatsapp.py` — New migration: backfill existing WhatsApp numbers into channel_identities
- `services/nova-core/tests/test_identity.py` — Added `TestResolveChannelIdentity` class (3 tests: known/unknown/coercion)
- `services/nova-core/tests/test_webhooks.py` — Added `test_whatsapp_last_active_update_atomic` (atomicity mock contract test)
- `services/nova-core/tests/test_telegram.py` — Added `test_telegram_last_active_update_atomic` (atomicity mock contract test)

## Decisions Made

- **Used migration 0009 instead of 0008**: The plan specified revision ID `0008` but `alembic/versions/0008_create_grocery_items.py` already exists. Used `0009` with `down_revision = "0008"` to avoid collision.
- **Also wrapped Telegram OTP path in `conn.transaction()`**: When moving the shared `attempts = 99` UPDATE into the WhatsApp `else:` branch's transaction, duplicated it inside the Telegram `if` branch as well, wrapped in its own transaction, to prevent regression and ensure consistency.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Migration revision ID conflict**
- **Found during:** Task 2 (Identity backfill)
- **Issue:** Plan specified `0008_backfill_channel_identities_whatsapp.py` with revision ID `0008`, but `alembic/versions/0008_create_grocery_items.py` (grocery_items table) already exists with that revision ID
- **Fix:** Created migration as `0009_backfill_channel_identities_whatsapp.py` with revision ID `0009` and `down_revision = "0008"`
- **Files modified:** `services/nova-core/alembic/versions/0009_backfill_channel_identities_whatsapp.py` (created)
- **Verification:** Migration file exists with correct revision chain (0007 ← 0008 ← 0009)
- **Committed in:** `2dd7132` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Required adjustment to migration numbering. No scope creep — changes are within the plan's intent.

## Issues Encountered

- **AsyncMock RuntimeWarnings in atomicity tests**: The `test_whatsapp_last_active_update_atomic` and `test_telegram_last_active_update_atomic` tests emit `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` from Python 3.13+ AsyncMock internals when using mock async context managers. This is a known cosmetic issue with AsyncMock — the tests pass correctly and all assertions hold.
- Pre-existing tests (`test_known_user_runs_agent`) already exhibit the same warning pattern, confirming this is a general test infrastructure concern, not specific to this phase.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Multi-channel identity resolution is unified. All channels (WhatsApp, Telegram) now go through `channel_identities` for identity resolution.
- WhatsApp numbers backfilled into `channel_identities` via migration 0009.
- Ready for Phase 32 (Household Coordination) where identity resolution will be used across channels.

---
*Phase: 21-multi-channel-identity-last-active-tracking*
*Completed: 2026-07-12*

## Self-Check: PASSED

All 10 expected files exist and both commits (ca72b4d, 2dd7132) are present in git history.
