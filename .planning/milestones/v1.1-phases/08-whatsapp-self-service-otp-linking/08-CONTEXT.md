# Phase 8: WhatsApp Self-Service OTP Linking - Context

**Gathered:** 2026-07-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Allows household members to securely link and verify their WhatsApp numbers dynamically via the dashboard, using a Meta-approved AUTHENTICATION message template with a rate-limited, single-use, expiring verification OTP. Scoped to ONBOARD-01 through ONBOARD-05.

</domain>

<decisions>
## Implementation Decisions

- **OTP Generation & Security**:
  - Generate a secure 6-digit random verification code.
  - Verification codes expire in 10 minutes.
  - Maximum of 3 guessing attempts before the code is invalidated.
- **Uniqueness Constraint**:
  - A WhatsApp number can only be linked to a single user at any time. Reassigning a number already claimed by another active user is rejected.
- **Mocking for Development/Testing**:
  - Meta template sending will be logged to console if credentials are unset to prevent blocking development.
- **UI Integration**:
  - Add a dedicated, beautifully styled "WhatsApp Linking & Identity" section to the bottom of the dashboard layout.
- **API Endpoints**:
  - `GET /api/preferences` - Retrieves current linked numbers and settings.
  - `POST /api/preferences/request-code` - Validates constraints, generates OTP, sends message.
  - `POST /api/preferences/verify-code` - Validates code, links the number to the user's profile.

</decisions>

<code_context>
## Existing Code Insights

- `user_preferences` table from Phase 7 stores the `whatsapp_number` field.
- `whatsapp_verification_codes` table from Phase 7 is ready to hold OTP attempts, codes, and expirations.
- `app/whatsapp.py` has `send_whatsapp_message` which can be used to send the OTP (mocked template during dev).

</code_context>

<specifics>
## Specific Ideas

See `08-PLAN.md`.

</specifics>

<deferred>
## Deferred Ideas

None.
