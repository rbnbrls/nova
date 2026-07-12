---
phase: 14-whatsapp-otp-self-service-linking
verified: 2026-07-12T16:10:00Z
status: passed
score: 6/6 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps: []
human_verification:
  - test: |
      1. Open the dashboard at http://localhost:PORT/static/index.html (or through the app).
      2. Click "Link WhatsApp" button in the preferences panel.
      3. Verify the modal appears with correct styling (glass-panel look, backdrop blur, centered).
      4. Switch between Ruben/Méral tabs in the modal — verify the active state changes.
      5. Enter a phone number and click "Send Code". With no backend running, verify a network error is displayed.
      6. Click Cancel — verify modal closes.
      7. Verify the existing preferences panel still shows the current linked number correctly.
      8. Verify the existing briefing and DND settings still function.
    expected: |
      - Modal renders correctly with all three states (number entry, code entry, result)
      - Identity selector works and highlights active user
      - API error handling shown correctly as modal error messages
      - Modal can be dismissed via Cancel, Close, or overlay click
      - Existing settings panels are unaffected by the new modal
    why_human: |
      UI appearance, transitions, and visual correctness require a human to verify in a browser.
      Automated tests verify API correctness and code structure; visual polish is not testable via pytest.
---

# Phase 14: WhatsApp OTP Self-Service Linking Verification Report

**Phase Goal:** Household members can link, verify, or replace their own WhatsApp number entirely through the dashboard, with no admin or env-var edit required.

**Verified:** 2026-07-12T16:10:00Z
**Status:** human_needed (all automated checks pass; modal UI needs visual verification)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can start WhatsApp-linking from the dashboard by selecting their household identity | ✓ VERIFIED | `index.html` (line 64: Link WhatsApp button, lines 128-167: modal with Ruben/Méral identity tabs). `app.js` (lines 290-312: modal open handler and identity tab switching). `main.py` (line 210: `/dashboard/link-whatsapp/start` endpoint accepts `{user, number}`). |
| 2 | Entering a valid E.164 number dispatches an OTP via the Meta `whatsapp_authentication` template | ✓ VERIFIED | `whatsapp.py` (lines 152-197: `send_whatsapp_otp` with AUTHENTICATION template payload). `main.py` (line 277: `await send_whatsapp_otp(clean_number, code)`). Test `test_start_success` verifies flow. |
| 3 | Codes are single-use, time-limited (5 min), rate-limited (1 per 5 min per number); incorrect guesses rejected with attempt tracking | ✓ VERIFIED | Single-use: `/verify` sets attempts=99 on success (line 357). Time-limited: `expires_at = now() + 5min` (line 261), query filters `expires_at > now()` (line 308). Rate-limited: `COUNT(*) ... created_at > now() - interval '5 minutes'` (lines 247-252), returns 429. Wrong guesses: code comparison (lines 327-342) with remaining-attempts message. Tests: `test_start_rate_limit_exceeded`, `test_verify_wrong_code`, `test_verify_exhausted_attempts`, `test_verify_expired_code`. |
| 4 | Claiming a number already linked to another user is rejected with a message naming the current owner | ✓ VERIFIED | `main.py` (lines 229-243): DB query for existing_owner, returns 400 `f"This number is already linked to {existing_owner}"`. UNIQUE constraint on `user_preferences.whatsapp_number` enforces at DB level. Test `test_start_claim_conflict` verifies this. |
| 5 | Existing linked user can re-link/replace through the same flow | ✓ VERIFIED | `/verify` endpoint (lines 345-352): `INSERT INTO user_preferences ... ON CONFLICT (user_id) DO UPDATE SET whatsapp_number = EXCLUDED.whatsapp_number`. This atomically handles both first-time linking and re-linking. Test `test_verify_success` verifies the DB operations. |
| 6 | Meta API delivery failures are surfaced to the user with a retry option | ✓ VERIFIED | `whatsapp.py` (lines 194-197): raises `RuntimeError` on Meta API failure. `main.py` (lines 276-282): catches RuntimeError, returns 502 with "Failed to send verification code. Please try again." Test `test_start_meta_api_failure` verifies 502 with retry message. |

**Score:** 6/6 truths verified (0 behavior-unverified, 0 overrides applied)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `app/channels/whatsapp.py` — `send_whatsapp_otp` | OTP delivery via Meta AUTHENTICATION template | ✓ VERIFIED | Exists at line 152, imports correctly, constructs `whatsapp_authentication` payload, raises RuntimeError on failure, mocks in dev mode |
| `app/main.py` — `/dashboard/link-whatsapp/start` | Start OTP linking | ✓ VERIFIED | Exists at line 210, validates user/format/conflict/rate-limit, generates code, sends OTP |
| `app/main.py` — `/dashboard/link-whatsapp/verify` | Verify OTP code | ✓ VERIFIED | Exists at line 290, validates with attempt tracking, links number on success |
| `app/models.py` — `LinkWhatsAppStartRequest` | Start request model | ✓ VERIFIED | Exists at line 69, fields `user` and `number` |
| `app/models.py` — `LinkWhatsAppVerifyRequest` | Verify request model | ✓ VERIFIED | Exists at line 74, fields `user` and `code` |
| `static/index.html` — modal overlay | Three-state modal | ✓ VERIFIED | Lines 128-167: number entry, code entry, result states |
| `static/app.js` — modal logic | Modal show/hide, API calls, state management | ✓ VERIFIED | Lines 242-435: modal state vars, all event handlers, API fetch calls |
| `static/style.css` — modal styles | Overlay, content, tabs, error display | ✓ VERIFIED | Lines 534-657: modal overlay, content, user tabs, error styles |
| `tests/test_whatsapp_otp.py` | 12 test cases | ✓ VERIFIED | All 12 tests pass covering models, /start validation paths, /verify pathways |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `whatsapp.py` → `main.py` | `send_whatsapp_otp` called by /start | Import at main.py line 31, call at line 277 | ✓ WIRED | `from .channels.whatsapp import ... send_whatsapp_otp`; caught `RuntimeError` raises 502 |
| `main.py` /verify → `user_preferences` | UPDATE respects UNIQUE + handles re-linking | `INSERT ... ON CONFLICT (user_id) DO UPDATE SET whatsapp_number = EXCLUDED.whatsapp_number` at line 346-352 | ✓ WIRED | Atomic INSERT with ON CONFLICT handles both first-time and re-linking |
| `main.py` /start → rate-limit query | `channel_verification_codes.created_at` 5-min window | `COUNT(*) ... WHERE created_at > now() - interval '5 minutes'` at lines 247-252 | ✓ WIRED | Correct 5-minute window per phone number |
| `index.html` modal → `app.js` fetch | Modal buttons call /dashboard/link-whatsapp/* | `fetch('/dashboard/link-whatsapp/start')` at line 329, `fetch('/dashboard/link-whatsapp/verify')` at line 361 | ✓ WIRED | Correct endpoint paths used; rate-limit (429) handled separately with wait-time message |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `/start` endpoint | `code` | `secrets.randbelow(900000) + 100000` | ✓ — Real random 6-digit code | ✓ FLOWING |
| `/start` endpoint | `clean_number` | User input, stripped of `+` | ✓ — Validated E.164 | ✓ FLOWING |
| `/start` endpoint | `rate_count` | `SELECT COUNT(*) FROM channel_verification_codes` with 5-min window | ✓ — Real DB query | ✓ FLOWING |
| `/verify` endpoint | Active code row | `SELECT ... FROM channel_verification_codes WHERE ... attempts < 3 AND expires_at > now()` | ✓ — Real DB query with temporal filter | ✓ FLOWING |
| `/verify` endpoint | `user_preferences.whatsapp_number` | `INSERT ... ON CONFLICT DO UPDATE` | ✓ — Real DB INSERT/UPDATE | ✓ FLOWING |
| Modal UI | `linked_number` | `fetchPreferences()` → `/api/preferences` | ✓ — Real API fetch, updates after verify success | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| All 12 WhatsApp OTP tests | `pytest tests/test_whatsapp_otp.py -v` | 12 passed in 0.32s | ✓ PASS |
| Models import and validate | `python3 -c "from app.models import ..."` | Models OK | ✓ PASS |
| `send_whatsapp_otp` signature | `python3 -c "inspect.signature(...)"` | Signature OK (to_number, code) | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| ONBOARD-01 | ROADMAP.md | User can start WhatsApp-linking from dashboard by selecting their household identity | ✓ SATISFIED | Modal overlay with Ruben/Méral identity tabs. API accepts `{user, number}`. |
| ONBOARD-02 | ROADMAP.md | User enters a WhatsApp number and Nova sends a one-time verification code via Meta AUTHENTICATION template | ✓ SATISFIED | `send_whatsapp_otp` sends via `whatsapp_authentication` template. `/start` endpoint dispatches OTP. |
| ONBOARD-03 | ROADMAP.md | User confirms code on dashboard; codes single-use, expire, rate-limited against guessing | ✓ SATISFIED | Single-use (attempts=99 after use), 5-min expiry, 3-attempt limit, rate-limit 1/5min. Tests cover all paths. |
| ONBOARD-04 | ROADMAP.md | Number linked to only one user; claiming already-linked number rejected | ✓ SATISFIED | Claim conflict check + UNIQUE constraint. Test `test_start_claim_conflict` passes. |
| ONBOARD-05 | ROADMAP.md | User can re-link/replace their linked WhatsApp number | ✓ SATISFIED | `INSERT ON CONFLICT (user_id) DO UPDATE` handles re-linking atomically. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| (none) | - | No TBD/FIXME/XXX/HACK markers found in any modified files | - | - |
| (none) | - | No stub implementations or placeholder components found | - | - |
| (none) | - | All `placeholder-loader`, `placeholder` uses are legitimate CSS/HTML (not stubs) | - | - |

### Human Verification Required

**Source:** Harvested from PLAN.md Task 3 `<verify><human-check>` block (deferred from automated verification).

### 1. Dashboard Modal UI Verification

**Test:**
1. Open the dashboard at `http://localhost:PORT/static/index.html` (or through the app).
2. Click "Link WhatsApp" button in the preferences panel.
3. Verify the modal appears with correct styling (glass-panel look, backdrop blur, centered).
4. Switch between Ruben/Méral tabs in the modal — verify the active state changes.
5. Enter a phone number and click "Send Code". With no backend running, verify a network error is displayed.
6. Click Cancel — verify modal closes.
7. Verify the existing preferences panel still shows the current linked number correctly.
8. Verify the existing briefing and DND settings still function.

**Expected:**
- Modal renders correctly with all three states (number entry, code entry, result).
- Identity selector works and highlights active user.
- API error handling shown correctly as modal error messages.
- Modal can be dismissed via Cancel, Close, or overlay click.
- Existing settings panels are unaffected by the new modal.

**Why human:** UI appearance, transitions, and visual correctness require a human to verify in a browser. Automated tests verify API correctness and code structure; visual polish is not testable via pytest.

### Pre-existing Test Failures

**2 pre-existing failures in `test_onboarding.py` confirmed as NOT caused by this phase:**
- `test_request_code_success` — Patches incorrect import path (`app.whatsapp.send_whatsapp_message` vs `app.main.send_whatsapp_message`)
- `test_verify_code_success` — Mock fetchrow missing `channel` field, causing `KeyError: 'channel'`

These failures exist in the codebase independently of this phase's changes. All 12 new WhatsApp OTP tests pass cleanly.

### Gaps Summary

**No gaps found.** All 6 must-have truths are verified against the codebase. The only outstanding items are:

1. **Human verification of modal UI** — visual appearance and interaction flow require a human to validate in a browser (harvested from PLAN.md).
2. **2 pre-existing test failures** — documented in Phase 13 as pre-existing, confirmed still pre-existing, not caused by this phase.

---

_Verified: 2026-07-12T16:10:00Z_
_Verifier: the agent (gsd-verifier)_
