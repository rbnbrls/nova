# Phase 8: WhatsApp Self-Service OTP Linking - Plan

**Status:** Ready

## Goal

Allows household members to securely link and verify their WhatsApp numbers dynamically via the dashboard, using a Meta-approved AUTHENTICATION message template with a rate-limited, single-use, expiring verification OTP.

## Depends On

Phase 7.

## Requirements

ONBOARD-01 through ONBOARD-05 (see `.planning/REQUIREMENTS.md`)

## Success Criteria (what must be TRUE)

1. User can start a WhatsApp-linking flow from the dashboard by selecting their household identity (Ruben or Méral).
2. User enters a WhatsApp number and receives a one-time verification code on that number via a Meta-approved AUTHENTICATION template.
3. User confirms the code on the dashboard and the number is linked only after correct verification; codes are single-use, expire, and are rate-limited against guessing.
4. Attempting to claim a WhatsApp number already linked to another user is rejected, not silently reassigned.
5. A user with an existing linked number can re-link/replace it with a new number through the same flow.

## Approach / Task Breakdown

1. **`services/nova-core/app/main.py` — API Endpoints**:
   - Create `GET /api/preferences` to fetch linked numbers for Ruben & Méral.
   - Create `POST /api/preferences/request-code` to validate and send OTP codes.
   - Create `POST /api/preferences/verify-code` to verify codes and update DB links.
2. **`services/nova-core/static/index.html` — Layout additions**:
   - Add preferences configuration section at the bottom.
3. **`services/nova-core/static/app.js` — Frontend JS logic**:
   - Fetch preferences and handle link code verification cycles.
4. **`services/nova-core/static/style.css` — CSS styling**:
   - Style settings panels, selectors, text inputs, buttons, and alert highlights.
5. **`services/nova-core/tests/test_onboarding.py` — Testing**:
   - Test number validation, expiration limits, rate limit bounds, and successful database update.
