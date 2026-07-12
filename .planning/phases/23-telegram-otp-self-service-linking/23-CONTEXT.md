# Phase 23 Context: Telegram OTP Self-Service Linking

## Source
ROADMAP.md SCs are self-explanatory.

## Decisions
- Follow Phase 14 (WhatsApp OTP) patterns closely: dashboard modal, identity picker, OTP via Telegram message
- Reuse channel_verification_codes table (has channel column)
- No AUTHENTICATION template needed (Telegram is direct messaging)
- Rate limiting and expiry same as Phase 14: 5-min TTL, 3 attempts, 1 code per 5 min
