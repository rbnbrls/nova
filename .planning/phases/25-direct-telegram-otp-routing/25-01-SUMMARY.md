---
phase: 25-direct-telegram-otp-routing
plan: 01
subsystem: api
tags: [telegram, otp, routing, verification]
requires:
  - phase: 23-telegram-otp-self-service-linking
    provides: send_telegram_otp helper, channel_identities infrastructure
provides:
  - Direct Telegram OTP routing in /api/preferences/request-code (channel=telegram)
affects: []
tech-stack:
  added: []
  patterns:
    - Telegram OTP delivery bypasses send_to_user dispatcher to guarantee Telegram-only routing
key-files:
  created: []
  modified:
    - services/nova-core/app/main.py
key-decisions:
  - "Fix already applied in commit 223ad60 (part of Phase 34) — plan verification confirms correctness"
patterns-established:
  - "Telegram OTP delivery always goes through send_telegram_otp() directly, never through the channel dispatcher"
requirements-completed:
  - TGOTP-02
coverage:
  - id: D1
    description: "/api/preferences/request-code with channel='telegram' calls send_telegram_otp directly instead of send_to_user dispatcher"
    requirement: TGOTP-02
    verification:
      - kind: unit
        ref: "grep -c send_telegram_otp services/nova-core/app/main.py"
        status: pass
      - kind: unit
        ref: "grep -c send_to_user services/nova-core/app/main.py"
        status: pass
      - kind: integration
        ref: "pytest tests/test_whatsapp_otp.py -x -q"
        status: pass
      - kind: integration
        ref: "pytest tests/test_telegram.py -x -q"
        status: pass
    human_judgment: false
  - id: D2
    description: "WhatsApp OTP path is unchanged — still uses send_whatsapp_message"
    verification:
      - kind: unit
        ref: "grep -n send_whatsapp_message services/nova-core/app/main.py"
        status: pass
    human_judgment: false
duration: 5min
completed: 2026-07-12
status: complete
---

# Phase 25: Direct Telegram OTP Routing Summary

**Telegram OTP routing in `/api/preferences/request-code` already uses `send_telegram_otp` directly — fix was pre-applied in an earlier commit**

## Background

The plan's objective was to replace `send_to_user()` dispatcher call with a direct `send_telegram_otp()` call in the `/api/preferences/request-code` endpoint when `channel='telegram'`. This ensures Telegram OTPs always go through the Telegram channel and never fall back to WhatsApp via the dispatcher's `last_active_channel` routing.

## Finding

Upon inspection, the fix was already applied in commit `223ad60` (part of Phase 34 — email action extraction). The production code at `services/nova-core/app/main.py` already:

1. Uses `send_telegram_otp(req.user, code)` directly for `channel='telegram'` requests
2. Raises HTTP 502 if `send_telegram_otp` returns `False` (no linked chat_id)
3. Has no reference to `send_to_user` or `from .channels.dispatcher import send_to_user`
4. Leaves the WhatsApp OTP path (`send_whatsapp_message`) unchanged

The import at line 33 (`from .channels.telegram import ... send_telegram_otp`) was already in place.

## Verification Results

| Check | Status |
|-------|--------|
| `send_to_user` in main.py | 0 matches |
| `send_telegram_otp` in main.py | 3 matches (import + 2 call sites) |
| `test_whatsapp_otp.py` | 12 passed |
| `test_telegram.py` | 25 passed |
| `test_webhooks.py` + related | 25 passed, 1 pre-existing failure (`test_outbound.py::test_send_dnd_queues_message` — unrelated to OTP) |

## Deviations from Plan

**None** — the plan's objective was verified as already met. No code changes were required.

## Commit History

The fix was delivered in:
- `223ad60` — feat(34-01): add email action extraction and reply drafting (included the Telegram OTP routing fix)

No new commits were created for this plan since the code was already correct.

## Next Phase Readiness

- Direct Telegram OTP routing is confirmed working in the request-code endpoint
- No blockers for dependent phases
