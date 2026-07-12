---
phase: 25-direct-telegram-otp-routing
verified: 2026-07-12T16:30:00Z
status: passed
score: 6/6 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps: []
deferred: []
behavior_unverified_items: []
human_verification: []
---

# Phase 25: Direct Telegram OTP Routing Verification Report

**Phase Goal:** Telegram OTP verification codes route correctly through the Telegram channel without falling back to WhatsApp.

**Verified:** 2026-07-12T16:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | Telegram OTP verification codes route through the Telegram channel, not WhatsApp | ✓ VERIFIED | `services/nova-core/app/main.py` lines 758-760: `if req.channel == "telegram": ... sent = await send_telegram_otp(req.user, code)` — directly calls Telegram OTP function, no dispatcher involved |
| 2 | `send_telegram_otp` is the only delivery path for Telegram verification codes | ✓ VERIFIED | Both call sites in `main.py` use `send_telegram_otp` directly: line 527 (`/dashboard/link-telegram/send-code`) and line 760 (`/api/preferences/request-code`). No `send_to_user` reference exists in `main.py`. |
| 3 | No fallback to WhatsApp for Telegram OTP scenarios | ✓ VERIFIED | The `channel='telegram'` branch (lines 758-768) raises HTTP 502 on failure — does not call `send_whatsapp_message` or `send_to_user`. WhatsApp path (lines 769-773) is separate in the `else` block. |
| 4 | OTP verification codes are sent via Telegram when user is linking a Telegram account | ✓ VERIFIED | `send_telegram_otp(req.user, code)` invoked at line 760 when `req.channel == "telegram"`. Imported at line 33 from `.channels.telegram`. |
| 5 | Routing decision uses `channel_identities` table to determine delivery channel | ✓ VERIFIED | `send_telegram_otp()` in `services/nova-core/app/channels/telegram.py` lines 305-312: `SELECT ci.channel_id FROM channel_identities ci JOIN users u ON ci.user_id = u.id WHERE u.name = $1 AND ci.channel = 'telegram'` |
| 6 | WhatsApp OTP path unchanged | ✓ VERIFIED | WhatsApp path at lines 769-773 still uses `send_whatsapp_message(clean_number, otp_message)` — same as before. Import at line 691 inside `request_code`. |

**Score:** 6/6 truths verified (0 present, behavior-unverified)

### Deferred Items

No deferred items — no later phase in this milestone addresses Telegram OTP routing.

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `services/nova-core/app/main.py` | request-code endpoint sends Telegram OTP via `send_telegram_otp`, not `send_to_user` dispatcher | ✓ VERIFIED | Line 33 imports `send_telegram_otp`; line 760 calls it directly for `channel='telegram'` requests. No `send_to_user` import or call exists in `main.py`. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `/api/preferences/request-code` with `channel='telegram'` | `send_telegram_otp` | Direct function call at line 760 | ✓ WIRED | `await send_telegram_otp(req.user, code)` — no dispatcher routing |
| `/dashboard/link-telegram/send-code` | `send_telegram_otp` | Direct function call at line 527 | ✓ WIRED | Already correct from Phase 23 — uses `send_telegram_otp` directly |
| `send_telegram_otp` | `channel_identities` table | SQL query in telegram.py lines 305-312 | ✓ WIRED | Resolves user_name → chat_id via `channel_identities` join |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `send_telegram_otp` | `code` (6-digit OTP) | `secrets.randbelow(900000) + 100000` at line 739 in `request_code` | ✓ Dynamic per-request token | ✓ FLOWING |
| `send_telegram_otp` | `chat_id` | `SELECT ci.channel_id FROM channel_identities` at lines 305-312 in telegram.py | ✓ Real DB query | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| `send_telegram_otp` exists and is importable | `rg "send_telegram_otp" services/nova-core/app/main.py` | 3 matches (import + 2 call sites) | ✓ PASS |
| `send_to_user` NOT used in main.py | `rg "send_to_user" services/nova-core/app/main.py` | 0 matches | ✓ PASS |
| `test_telegram.py` passes | `python -m pytest services/nova-core/tests/test_telegram.py -x -q` | 25 passed | ✓ PASS |
| `test_whatsapp_otp.py` passes | `python -m pytest services/nova-core/tests/test_whatsapp_otp.py -x -q` | 12 passed | ✓ PASS |

### Probe Execution

Step 7c: SKIPPED (no probes declared in PLAN or found in conventional locations; phase is a routing fix with code-presence verification, not a migration/tooling phase requiring runnable probes)

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| TGOTP-02 | 25-01-PLAN.md | Dashboard sends a verification code as a Telegram message; user confirms the code on the dashboard | ✓ SATISFIED | `send_telegram_otp` called directly at line 760 for `channel='telegram'`; `channel_identities` query resolves delivery target; 502 on failure |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | — | — | No anti-patterns found |

No TBD, FIXME, XXX, TODO, HACK, PLACEHOLDER, or stub patterns found in any modified files.

### Human Verification Required

None. All truths are statically verifiable through code structure and test results. No runtime state transitions, cancellation invariants, or ordering requirements are asserted.

### Gaps Summary

No gaps found. All success criteria and must-haves are satisfied.

The fix described in the plan was already applied in commit `223ad60` (part of Phase 34 — email action extraction). The code at `services/nova-core/app/main.py` lines 758-768 correctly uses `send_telegram_otp(req.user, code)` directly for `channel='telegram'` requests, bypassing the `send_to_user` dispatcher entirely. No fallback to WhatsApp exists for Telegram OTP scenarios.

---

_Verified: 2026-07-12T16:30:00Z_
_Verifier: the agent (gsd-verifier)_
