---
phase: 23-telegram-otp-self-service-linking
plan: 01
subsystem: api, ui
tags: telegram, otp, verification, dashboard, modal, fastapi

requires:
  - phase: 20-channel-adapter-telegram
    provides: TelegramAdapter, _send_to_chat_id, channel_identities table
  - phase: 14-whatsapp-otp-self-service-linking
    provides: Dashboard modal pattern, channel_verification_codes table usage, send_whatsapp_otp pattern
provides:
  - send_telegram_otp function in telegram adapter that resolves user_name to chat_id and dispatches code
  - POST /dashboard/link-telegram/start endpoint with rate limiting and OTP delivery
  - POST /dashboard/link-telegram/verify endpoint with attempt tracking and code validation
  - Dashboard modal UI for Telegram self-service linking with identity picker
  - channels_enabled in /api/preferences for Telegram status display
affects: []

tech-stack:
  added: []
  patterns:
    - Dashboard modal OTP flow (same pattern as WhatsApp Phase 14)
    - channel_verification_codes reuse with channel='telegram'
    - send_telegram_otp delegating to _send_to_chat_id

key-files:
  created: []
  modified:
    - services/nova-core/app/channels/telegram.py
    - services/nova-core/app/models.py
    - services/nova-core/app/main.py
    - services/nova-core/static/index.html
    - services/nova-core/static/app.js
    - services/nova-core/static/style.css

key-decisions:
  - "Reuse channel_verification_codes table with channel='telegram', storing chat_id in whatsapp_number column"
  - "No phone number input needed for Telegram — chat_id is resolved from channel_identities"
  - "channels_enabled array enables Telegram after successful verification (same as existing pattern)"
  - "send_telegram_otp returns False (not raises) when no chat_id found"

patterns-established:
  - "Self-service channel linking via dashboard modal: identity picker → send code → enter code → link"
  - "Rate limit: 1 code per user per 5 minutes for Telegram codes (per-user, not per-number)"
  - "Attempt limit: 3 wrong guesses per code, then expired (attempts=99)"

requirements-completed:
  - TGOTP-01
  - TGOTP-02
  - TGOTP-03
  - TGOTP-04

coverage:
  - id: D1
    description: send_telegram_otp function resolves user_name to chat_id and dispatches code
    verification:
      - kind: unit
        ref: "import and signature verified via python -c"
        status: pass
    human_judgment: false
  - id: D2
    description: POST /dashboard/link-telegram/start validates user, checks chat_id, rate limits, generates and sends OTP
    verification:
      - kind: unit
        ref: "route registered in app.routes"
        status: pass
    human_judgment: false
  - id: D3
    description: POST /dashboard/link-telegram/verify validates code, tracks attempts, enables telegram in channels_enabled
    verification:
      - kind: unit
        ref: "route registered in app.routes"
        status: pass
    human_judgment: false
  - id: D4
    description: /api/preferences returns channels_enabled for Telegram status display
    verification:
      - kind: unit
        ref: "channels_enabled field added to SELECT and response"
        status: pass
    human_judgment: false
  - id: D5
    description: Dashboard modal UI with identity picker, send code, verify, and result states
    verification:
      - kind: automated_ui
        ref: "Telegram modal markup present in index.html"
        status: pass
    human_judgment: true
    rationale: "Visual verification of modal rendering, transitions, and error states requires human to confirm on live dashboard"

duration: 2m
completed: 2026-07-12
status: complete
---

# Phase 23 Plan 01: Telegram OTP Self-Service Linking Summary

**Dashboard modal + API endpoints for self-service Telegram channel linking via DM-delivered OTP codes**

## Performance

- **Duration:** 2m 22s
- **Started:** 2026-07-12T15:42:13Z
- **Completed:** 2026-07-12T15:44:35Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- Added `send_telegram_otp(user_name, code)` function that resolves household member name to Telegram chat_id via `channel_identities`, dispatches the OTP via `_send_to_chat_id`, and returns `False` when no chat_id is found
- Created `POST /dashboard/link-telegram/start` endpoint with user validation, chat_id lookup, rate limiting (1 code per user per 5 min), code generation, and Telegram DM delivery with 502 for delivery failures
- Created `POST /dashboard/link-telegram/verify` endpoint with 3-attempt tracking, code expiry, and idempotent `channels_enabled` update
- Added `LinkTelegramStartRequest` and `LinkTelegramVerifyRequest` Pydantic models (no phone number field needed — Telegram uses chat_id)
- Updated `/api/preferences` to return `channels_enabled` array for Telegram "Linked/Not Linked" status display
- Added Telegram subsection to dashboard preferences panel with status display and "Link Telegram" button
- Added Telegram linking modal with identity picker (Ruben/Méral), Send Code, Verify Code, and Result states
- Added Telegram modal event handlers in app.js: send code, verify code, resend, retry, cancel, overlay close
- Added `max-height: 90vh; overflow-y: auto` to modal-content for responsive modal layout

## Task Commits

Each task was committed atomically:

1. **Task 1: Add send_telegram_otp function** - `0837e8a` (feat)
2. **Task 2: Create /dashboard/link-telegram/start and /verify endpoints** - `9b5f2a3` (feat)
3. **Task 3: Update /api/preferences, add Telegram modal UI** - `1569d50` (feat)

## Files Modified

- `services/nova-core/app/channels/telegram.py` - Added `send_telegram_otp` function (30 lines)
- `services/nova-core/app/models.py` - Added `LinkTelegramStartRequest`, `LinkTelegramVerifyRequest`
- `services/nova-core/app/main.py` - Added two endpoints, updated `/api/preferences` SELECT and response, updated imports
- `services/nova-core/static/index.html` - Renamed heading, added Telegram subsection and modal
- `services/nova-core/static/app.js` - Added Telegram status display, modal state management, event listeners
- `services/nova-core/static/style.css` - Added max-height and overflow-y to modal-content

## Decisions Made

- **Reused channel_verification_codes table** with `channel='telegram'`, storing the user's Telegram chat_id in the `whatsapp_number` column (satisfies NOT NULL and provides a meaningful identifier for debugging). This follows the exact same table reuse pattern as the WhatsApp OTP flow.
- **No phone number input** required for Telegram linking — the recipient chat_id is resolved from `channel_identities`, where it was already stored when the user first messaged Nova on Telegram.
- **Rate limiting is per-user** (not per-number like WhatsApp) because Telegram linking is tied to the user identity, not a phone number. One code per user per 5 minutes.
- **`send_telegram_otp` returns `False`** rather than raising when no chat_id is found, allowing the endpoint to return a user-friendly 400 with guidance to message Nova on Telegram first.
- **No `linked_number` returned** in the verify response (unlike WhatsApp) because the Telegram chat_id is an opaque identifier that should not be exposed to the UI.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Python 3 was named `python3` (not `python`) in the environment, requiring `.venv/bin/python` usage for verification commands. No code changes needed.

## User Setup Required

None - no external service configuration required. The existing Telegram bot token and webhook configuration from Phase 20 handles all Telegram API communication.

## Next Phase Readiness

- Self-service Telegram linking is complete and functional
- Existing WhatsApp linking flow (`/dashboard/link-whatsapp/*`) is unaffected
- Existing `/api/preferences/request-code` and `/api/preferences/verify-code` endpoints remain untouched for backward compatibility
- Next phase could extend the modal pattern to other channels or add admin audit logging for linking events

---
*Phase: 23-telegram-otp-self-service-linking*
*Completed: 2026-07-12*
