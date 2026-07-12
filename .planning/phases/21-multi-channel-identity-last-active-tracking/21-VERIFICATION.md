---
phase: 21-multi-channel-identity-last-active-tracking
verified: 2026-07-12T16:30:00Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps: []
---

# Phase 21: Multi-Channel Identity & Last-Active Tracking Verification Report

**Phase Goal:** Both inbound channels update last-active tracking atomically; identity resolution works across all channels via `channel_identities`.

**Verified:** 2026-07-12T16:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | WhatsApp handler's last_inbound_at + last_active_channel UPDATEs succeed or fail as a single unit | ✓ VERIFIED | `services/nova-core/app/channels/whatsapp.py` lines 344-350: `async with conn.transaction()` wraps both UPDATEs. Test `test_whatsapp_last_active_update_atomic` in `test_webhooks.py` verifies `conn.transaction()` is called via mock. |
| 2 | Telegram handler's last_inbound_at + last_active_channel UPDATEs succeed or fail as a single unit | ✓ VERIFIED | `services/nova-core/app/channels/telegram.py` lines 271-277: `async with conn.transaction()` wraps both UPDATEs. Test `test_telegram_last_active_update_atomic` in `test_telegram.py` verifies `conn.transaction()` is called via mock. |
| 3 | channels/identity.py resolve() returns a household User for any channel with a row in channel_identities | ✓ VERIFIED | `services/nova-core/app/channels/identity.py` line 13: `async def resolve(channel: str, channel_id: str) -> User`. Returns `User(name=row["name"])` for known identities, `HOUSEHOLD` for unknown. Tests `test_resolve_returns_user_for_known_channel_id` and `test_resolve_returns_household_for_unknown` verify both paths. |
| 4 | Existing WhatsApp numbers in user_preferences are reachable via channel_identities.resolve(channel='whatsapp', ...) | ✓ VERIFIED | Migration `0009_backfill_channel_identities_whatsapp.py` copies existing `whatsapp_number` from `user_preferences` into `channel_identities`. Startup seed (`db.py` line 85-93) also mirrors WhatsApp numbers during init. resolve() queries `channel_identities` joined to `users` — both code paths verified. |
| 5 | New WhatsApp OTP links write to both user_preferences and channel_identities atomically | ✓ VERIFIED | `services/nova-core/app/main.py` lines 826-849: `async with conn.transaction()` wraps `INSERT INTO user_preferences` and `INSERT INTO channel_identities (channel='whatsapp')` and `UPDATE channel_verification_codes SET attempts = 99`. All three statements in a single transaction. |

**Score:** 5/5 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `channels/whatsapp.py` | Transaction wrapping for last-active UPDATEs | ✓ VERIFIED | Line 345: `async with conn.transaction()` wraps both UPDATEs. `SET last_active_channel = 'whatsapp'` present at line 348. All existing tests pass. |
| `channels/telegram.py` | Transaction wrapping for last-active UPDATEs | ✓ VERIFIED | Line 272: `async with conn.transaction()` wraps both UPDATEs. `SET last_active_channel = 'telegram'` present at line 275. All existing tests pass. |
| `channels/identity.py` | resolve() returns User/HOUSEHOLD per identity.py patterns | ✓ VERIFIED | Signature: `async def resolve(channel: str, channel_id: str) -> User`. Imports `User, HOUSEHOLD` from `..identity`. Returns `User(name=row["name"])` or `HOUSEHOLD`. |
| `main.py` | channel_identities INSERT on WhatsApp OTP verify | ✓ VERIFIED | Lines 826-849: WhatsApp OTP path writes to both `user_preferences` and `channel_identities`. Transaction wraps both. Telegram OTP path also updated. |
| `db.py` | channel_identities INSERT on startup seed for WhatsApp | ✓ VERIFIED | Lines 84-93: Mirror WhatsApp number into `channel_identities` during startup seeding. |
| `alembic/versions/0009_backfill_channel_identities_whatsapp.py` | Migration to backfill existing WhatsApp numbers | ✓ VERIFIED | Revision `0009`, down_revision `0008`. `upgrade()` copies existing numbers; `downgrade()` deletes WhatsApp channel rows. |
| `tests/test_identity.py` | resolve + atomicity coverage | ✓ VERIFIED | `TestResolveChannelIdentity` class with 3 tests: known user, unknown (HOUSEHOLD), BIGINT coercion. All pass. |
| `tests/test_webhooks.py` | WhatsApp atomicity contract test | ✓ VERIFIED | `test_whatsapp_last_active_update_atomic` verifies `conn.transaction()` is called for WhatsApp handler. |
| `tests/test_telegram.py` | Telegram atomicity contract test | ✓ VERIFIED | `test_telegram_last_active_update_atomic` verifies `conn.transaction()` is called for Telegram handler. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| WhatsApp handler `process_incoming_whatsapp` | DB (users + user_preferences) | `async with conn.transaction()` | ✓ WIRED | Both UPDATEs share a single database transaction (line 344-350). |
| Telegram handler `process_incoming_telegram` | DB (users + user_preferences) | `async with conn.transaction()` | ✓ WIRED | Both UPDATEs share a single database transaction (line 271-277). |
| channels/identity.py resolve() | channel_identities table | `conn.fetchrow()` with JOIN on users | ✓ WIRED | Query at line 26-35 queries `channel_identities` joined to `users`. |
| main.py OTP verify (WhatsApp) | user_preferences + channel_identities | `conn.transaction()` wrapping both INSERTs | ✓ WIRED | Lines 826-849: Both INSERTs atomic within transaction. |
| db.py startup seed | channel_identities | `conn.execute()` after user_preferences seed | ✓ WIRED | Lines 84-93: WhatsApp numbers mirrored to channel_identities. |
| Migration 0009 | user_preferences → channel_identities | `INSERT INTO ... SELECT ... FROM user_preferences` | ✓ WIRED | Backfills existing numbers. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| channels/whatsapp.py UPDATEs | `user.name` | Inbound message sender → identity resolution | DB UPDATE with real user identity | ✓ FLOWING |
| channels/telegram.py UPDATEs | `user.name` | Inbound message sender → identity resolution | DB UPDATE with real user identity | ✓ FLOWING |
| channels/identity.py resolve() | `(channel, channel_id)` | Caller-provided args | Queries channel_identities → returns User or HOUSEHOLD | ✓ FLOWING |
| main.py OTP verify | `(user_id, whatsapp_number)` | Verification code row from DB | INSERTs into user_preferences + channel_identities | ✓ FLOWING |
| db.py startup seed | `(number, user_id)` | Config `NOVA_WHATSAPP_USERS` | INSERTs into user_preferences + channel_identities | ✓ FLOWING |
| Migration 0009 | `(user_id, whatsapp_number)` | Existing user_preferences rows | SELECT from user_preferences → INSERT into channel_identities | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Identity tests pass | `pytest services/nova-core/tests/test_identity.py -x -q` | 9 passed in 0.45s | ✓ PASS |
| Webhook tests pass (WhatsApp atomicity + regression) | `pytest services/nova-core/tests/test_webhooks.py -x -q` | 22 passed, 2 warnings in 0.50s | ✓ PASS |
| Telegram tests pass (Telegram atomicity + regression) | `pytest services/nova-core/tests/test_telegram.py -x -q` | 25 passed, 3 warnings in 0.40s | ✓ PASS |

Note: Warnings are known cosmetic `AsyncMock` `RuntimeWarning` issues documented in SUMMARY.md — they do not affect correctness.

### Probe Execution

No probes declared for this phase. Phase work is verified via pytest test suite and grep/file presence checks.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| CHAN-03 | 21-01-PLAN.md | Both inbound channels update `last_active_channel` atomically on every user message | ✓ SATISFIED | Both WhatsApp and Telegram handlers wrap last_inbound_at + last_active_channel in explicit transactions. channels/identity.py resolve() unified resolution. All 56 tests pass. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| services/nova-core/app/channels/telegram.py | 102 | "coming soon" placeholder text for `/tasks` command | ℹ️ Info | Pre-existing from Phase 20 — not related to Phase 21 scope. The `/tasks` and `/settings` command handlers are intentionally deferred. |

No blocker-level anti-patterns found. No TBD, FIXME, or XXX markers in any Phase 21 modified files.

### Human Verification Required

None — all must-haves are verifiable through code inspection and automated tests.

### Gaps Summary

No gaps found. All 5 truths verified, all artifacts present and substantive, all key links wired, all tests pass. Phase goal fully achieved.

---

_Verified: 2026-07-12T16:30:00Z_
_Verifier: the agent (gsd-verifier)_
