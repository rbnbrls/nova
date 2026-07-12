# Phase 14 Context: WhatsApp OTP Self-Service Linking

## Source
ROADMAP.md Phase 14 goal + success criteria.

## Decisions

### OTP Flow
- User starts from the dashboard (modal overlay, not a separate page)
- Select their household identity from a picker (populated from DB users table)
- Enter target WhatsApp number in E.164 format
- Code delivered via Meta AUTHENTICATION template (`whatsapp_authentication`)

### Security Rules
- **Single-use:** Each code can be used exactly once
- **Time-limited:** Codes expire after 5 minutes
- **Rate-limited:** Max 3 attempts per code, max 1 code per phone number per 5 minutes
- **Claim conflict:** If a number is already linked to another user, reject with a clear message (not silently reassign)
- **Re-linking:** An existing linked user can replace their number through the same flow — old number unlinked on success

### Error Handling
- If sending the OTP message fails (Meta API error), surface the error to the user with retry option
- Rate-limit breaches return a friendly wait-time message
- Wrong code attempts decrement remaining attempts; after 3 failures the code expires immediately

### Implementation Patterns
- Extend existing `channel_verification_codes` table (already has schema for this)
- Reuse `send_whatsapp_message` for template delivery
- Dashboard endpoint: `POST /dashboard/link-whatsapp/start` and `POST /dashboard/link-whatsapp/verify`
- Follow existing dashboard patterns (FastAPI routes in main.py, SSE for status)
- No new env vars — uses existing WhatsApp config

## Deferred Ideas
None.
