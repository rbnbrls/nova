---
phase: 14-whatsapp-otp-self-service-linking
plan: 01
subsystem: api, channels, ui
tags: whatsapp, meta, otp, authentication, pydantic, fastapi, dashboard, modal
requires:
  - phase: 13-db-preferences-and-identity-migration
    provides: DB-backed identity, user_preferences table, channel_verification_codes schema
provides:
  - send_whatsapp_otp function for Meta AUTHENTICATION template delivery
  - POST /dashboard/link-whatsapp/start and /dashboard/link-whatsapp/verify endpoints
  - Dashboard modal overlay with identity selection, number entry, code entry, result display
affects: [15-per-user-dynamic-scheduling, 23-telegram-otp-self-service-linking]
tech-stack:
  added: []
  patterns:
    - OTP delivery via Meta AUTHENTICATION template (pre-approved, no custom template needed)
    - Three-state dashboard modal overlay with identity selection
    - Per-phone-number rate limiting (1 code per 5 min)
    - Attempt tracking with automatic code expiry after 3 failures
key-files:
  created:
    - services/nova-core/tests/test_whatsapp_otp.py
  modified:
    - services/nova-core/app/channels/whatsapp.py
    - services/nova-core/app/models.py
    - services/nova-core/app/main.py
    - services/nova-core/static/index.html
    - services/nova-core/static/app.js
    - services/nova-core/static/style.css
key-decisions:
  - "Dedicated send_whatsapp_otp function separate from send_whatsapp_message per D-13 (reuse pattern, not modify)"
  - "Dedicated LinkWhatsAppStartRequest and LinkWhatsAppVerifyRequest models per D-14"
  - "Always writes channel='whatsapp' and leaves channel_id NULL per D-12"
  - "Attempts incremented before code comparison per D-11 (always counts toward limit)"
  - "Number uniqueness enforced via user_preferences.whatsapp_number UNIQUE constraint plus query check per D-07"
patterns-established:
  - "OTP delivery: Meta AUTHENTICATION template via dedicated function with mock mode and error raising"
  - "WhatsApp linking endpoints: separate from /api/preferences/*, under /dashboard/link-whatsapp/*"
  - "Dashboard modal: three-state UI pattern (number entry → code entry → result)"
requirements-completed: [ONBOARD-01, ONBOARD-02, ONBOARD-03, ONBOARD-04, ONBOARD-05]
coverage:
  - id: D1
    description: send_whatsapp_otp function delivers 6-digit OTP via Meta AUTHENTICATION template, with mock mode and RuntimeError on failure
    requirement: ONBOARD-01
    verification:
      - kind: unit
        ref: tests/test_whatsapp_otp.py#test_start_success
        status: pass
    human_judgment: false
  - id: D2
    description: POST /dashboard/link-whatsapp/start validates user/number, checks claim conflicts, enforces rate limit, generates code, sends OTP, returns code_sent
    requirement: ONBOARD-02
    verification:
      - kind: unit
        ref: tests/test_whatsapp_otp.py#test_start_success
        status: pass
      - kind: unit
        ref: tests/test_whatsapp_otp.py#test_start_user_not_found
        status: pass
      - kind: unit
        ref: tests/test_whatsapp_otp.py#test_start_invalid_number
        status: pass
      - kind: unit
        ref: tests/test_whatsapp_otp.py#test_start_claim_conflict
        status: pass
      - kind: unit
        ref: tests/test_whatsapp_otp.py#test_start_rate_limit_exceeded
        status: pass
      - kind: unit
        ref: tests/test_whatsapp_otp.py#test_start_meta_api_failure
        status: pass
    human_judgment: false
  - id: D3
    description: POST /dashboard/link-whatsapp/verify validates code with attempt tracking, links number on success, handles re-linking atomically
    requirement: ONBOARD-03
    verification:
      - kind: unit
        ref: tests/test_whatsapp_otp.py#test_verify_success
        status: pass
      - kind: unit
        ref: tests/test_whatsapp_otp.py#test_verify_wrong_code
        status: pass
      - kind: unit
        ref: tests/test_whatsapp_otp.py#test_verify_exhausted_attempts
        status: pass
      - kind: unit
        ref: tests/test_whatsapp_otp.py#test_verify_expired_code
        status: pass
      - kind: unit
        ref: tests/test_whatsapp_otp.py#test_verify_user_not_found
        status: pass
    human_judgment: false
  - id: D4
    description: Dashboard modal overlay with identity selection, number entry, code entry, and success/error states
    requirement: ONBOARD-04
    verification: []
    human_judgment: true
    rationale: UI interaction requires visual verification — open the dashboard, click Link WhatsApp, verify modal renders and transitions correctly
duration: 18min
completed: 2026-07-12
status: complete
---

# Phase 14 Plan 01: WhatsApp OTP Self-Service Linking Summary

**send_whatsapp_otp via Meta AUTHENTICATION template, two API endpoints, dashboard modal overlay — enabling household members to link their WhatsApp number through a self-service UI**

## Performance

- **Duration:** 18 min
- **Started:** 2026-07-12T13:37:33Z (approximate)
- **Completed:** 2026-07-12T13:55:33Z (approximate)
- **Tasks:** 3 (1 auto, 1 TDD with RED/GREEN, 1 auto)
- **Files modified:** 6

## Accomplishments

- `send_whatsapp_otp(to_number, code)` function delivering OTP via Meta's pre-approved `whatsapp_authentication` AUTHENTICATION template, with mock mode for development and RuntimeError propagation for user-facing retry
- `POST /dashboard/link-whatsapp/start` with full validation: user existence, number format, claim conflict checking (400 with owner name), rate limiting (429 with wait-time message), 6-digit code generation, OTP dispatch, and 502 on Meta API failure
- `POST /dashboard/link-whatsapp/verify` with attempt tracking (3 max, incremented before comparison), code comparison with remaining-attempts feedback, atomic number linking via INSERT ON CONFLICT, and automatic code consumption on success
- Dashboard modal overlay with three-state UI: identity & number entry, code entry with resend, success/error with auto-close and preferences refresh
- 12 unit tests covering all pathways (models, /start validation paths, /verify pathways)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add send_whatsapp_otp function** - `f93917e` (feat)
2. **Task 2a (RED): Add failing test file** - `338b8e3` (test)
3. **Task 2b (GREEN): Add models and endpoints** - `0e7927e` (feat)
4. **Task 2c (REFACTOR): Fix test assertion** - `bac27ea` (refactor)
5. **Task 3: Dashboard modal overlay** - `34de35c` (feat)

## Files Created/Modified

- `services/nova-core/app/channels/whatsapp.py` - Added `send_whatsapp_otp` function
- `services/nova-core/app/models.py` - Added `LinkWhatsAppStartRequest`, `LinkWhatsAppVerifyRequest` models
- `services/nova-core/app/main.py` - Added two new endpoints, updated imports
- `services/nova-core/static/index.html` - Replaced old inline WhatsApp form with modal-trigger button and modal overlay markup
- `services/nova-core/static/app.js` - Removed old inline handlers, added modal state management and event listeners
- `services/nova-core/static/style.css` - Added modal overlay, modal content, user tabs, error display, and input styles
- `services/nova-core/tests/test_whatsapp_otp.py` - 12 test cases covering all endpoint paths

## Decisions Made

- Used dedicated `send_whatsapp_otp` function separate from `send_whatsapp_message` — the AUTHENTICATION template payload shape differs (OTP code in body parameters, no `preview_url`), and errors must propagate for retry
- Used dedicated Pydantic models rather than extending the existing `RequestCodeRequest` — simpler, no backward-compat concerns
- Rate limit queries on `channel_verification_codes.created_at` with a 5-minute window — enforces 1 code per phone number, not per user
- Attempt increment happens before code comparison — always counts toward limit per D-11
- `INSERT ON CONFLICT (user_id) DO UPDATE SET whatsapp_number` handles both first-time linking and re-linking atomically

## Deviations from Plan

None - plan executed exactly as written.

### Pre-existing Test Failures

**2 pre-existing test failures in `test_onboarding.py` were confirmed as NOT caused by this plan:**
- `test_request_code_success` - Patches incorrect import path (`app.whatsapp.send_whatsapp_message` vs `app.main.send_whatsapp_message`)
- `test_verify_code_success` - Mock fetchrow missing `channel` field, causing `KeyError: 'channel'`

All 12 new tests pass. All other existing test suites unchanged.

## Issues Encountered

- `.venv` had missing dependencies — installed fastapi, pydantic, httpx, asyncpg, alembic, apscheduler via pip to run test suite
- Pre-existing test failures in `test_onboarding.py` confirmed as pre-existing, not caused by this plan's changes

## User Setup Required

None - no external service configuration required. Meta AUTHENTICATION template is pre-approved for all WhatsApp Business Accounts. Existing WhatsApp API credentials are reused.

## Next Phase Readiness

- OTP delivery and verification infrastructure ready for Phase 15 (Per-User Dynamic Scheduling) and Phase 23 (Telegram OTP Self-Service Linking)
- The `channel_verification_codes` schema already supports multi-channel verification codes via `channel` column
- Dashboard modal pattern (three-state overlay with API integration) ready for reuse in future self-service flows

---

*Phase: 14-whatsapp-otp-self-service-linking*
*Completed: 2026-07-12*

## Self-Check: PASSED

- All 7 created/modified files verified on disk
- All 5 commit hashes confirmed in git log
- All 12 WhatsApp OTP tests pass
- No TBD/FIXME/XXX markers left in code
