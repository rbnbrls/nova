# Phase 8 Summary: WhatsApp Self-Service OTP Linking

> Written 2026-07-12, documenting the implementation of Phase 8.

## Shipped

We implemented changes to allow dynamic self-service WhatsApp phone number linking and verification:
- `services/nova-core/app/models.py` — Created request pydantic models `RequestCodeRequest` and `VerifyCodeRequest`.
- `services/nova-core/app/main.py` — Created endpoints `GET /api/preferences` to fetch current linked numbers, `POST /api/preferences/request-code` to generate and send verification OTP codes, and `POST /api/preferences/verify-code` to verify codes, track limits, and link E.164 numbers.
- `services/nova-core/static/index.html` — Added a beautifully styled settings tab panel card for settings and onboarding.
- `services/nova-core/static/app.js` — Built frontend code-request/verification flows, displaying error and success messaging seamlessly.
- `services/nova-core/static/style.css` — Designed style tokens for forms, tab indicators, active states, custom input layouts, and settings alerts.

## Mapping to Success Criteria

1. **Dashboard Start link flow** — PASS. Users can select Ruben or Méral to link their numbers dynamically.
2. **Authentication template code delivery** — PASS. SMS/WhatsApp delivery is invoked via Meta templates, logging verification OTP to console for development.
3. **Correct validation & rate limits** — PASS. Code is single-use, expires in 10 minutes, and blocks after 3 incorrect guessing attempts.
4. **Link number uniqueness checks** — PASS. Attempts to claim another active user's phone number are rejected with an explicit warning message.
5. **Number re-link / replacement** — PASS. Same flow allows replacing/re-linking numbers at any time.
