# Requirements: Nova

**Defined:** 2026-07-12
**Core Value:** A private, fully local household assistant that Ruben & Méral can reach by text or voice, keeping a shared plan (tasks, calendar, important email) — reasoning and data never leave the house.

## v3.0 Requirements

Requirements for Milestone v3.0 Multi-Channel Support. Each maps to roadmap phases.

### Telegram Channel Foundation

- [x] **TGBOT-01**: User can message Nova via Telegram and receive a reply (full agent-loop parity with WhatsApp)
- [x] **TGBOT-02**: Telegram webhook verifies the `X-Telegram-Bot-Api-Secret-Token` header with constant-time comparison
- [x] **TGBOT-03**: Telegram `update_id` deduplication prevents duplicate agent executions on webhook retries
- [x] **TGBOT-04**: Nova sends replies to the user's Telegram chat_id (outbound `sendMessage`)

### Channel Preferences & Identity

- [x] **CHAN-01**: User's channel preference (Telegram, WhatsApp, or both) is stored in Postgres `user_preferences`
- [x] **CHAN-02**: `channel_identities` table maps Telegram chat_ids and WhatsApp phone numbers to household users
- [x] **CHAN-03**: Both inbound channels update `last_active_channel` atomically on every user message

### Push Gateway Refactor

- [x] **PUSH-01**: Morning briefing, weekly briefing, task reminders, and email alerts route to the user's last-active channel (not hardcoded to WhatsApp)
- [x] **PUSH-02**: DND-deferred messages queue and deliver to the correct channel when DND window ends
- [x] **PUSH-03**: A `NOVA_TELEGRAM_ENABLED` feature flag gates all new Telegram behavior; default OFF keeps WhatsApp-only safe

### Telegram Formatting

- [x] **TGFORMAT-01**: Telegram messages use HTML parse mode (not MarkdownV2) — bold, italic, links render correctly
- [x] **TGFORMAT-02**: Messages exceeding 4096 characters are chunked at paragraph boundaries with 1-second inter-chunk delays

### Telegram Onboarding

- [x] **TGOTP-01**: User initiates Telegram linking from the dashboard by selecting their household identity
- [x] **TGOTP-02**: Dashboard sends a verification code as a Telegram message; user confirms the code on the dashboard
- [x] **TGOTP-03**: Verification codes are single-use, time-limited, rate-limited, and reject already-linked chat_ids
- [x] **TGOTP-04**: User with an existing linked Telegram account can re-link/replace with a new chat_id

### Telegram Bot Commands

- [x] **CMD-01**: Bot registers a `/help`, `/tasks`, `/settings` command menu via `setMyCommands`
- [x] **CMD-02**: `/help` returns a text summary of Nova's capabilities

## v2 Requirements

### Telegram UX Enhancements

- **TGUX-01**: Inline keyboard buttons for OTP confirmation (tap-to-confirm)
- **TGUX-02**: Streaming reply drafts (`sendMessageDraft`) during LLM reasoning
- **TGUX-03**: Deep linking for one-tap account linking (`t.me/NovaBot?start=link_<token>`)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Group chat support | Completely different message model; household of 2 uses DMs |
| Telegram voice transcription | ESPHome/voice channel already covers voice input |
| MarkdownV2 formatting | HTML parse mode covers all needs without escaping complexity |
| Per-channel DND preferences | Single DND-per-user is sufficient for v3.0 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| TGBOT-01 | Phase 14 | Complete |
| TGBOT-02 | Phase 14 | Complete |
| TGBOT-03 | Phase 14 | Complete |
| TGBOT-04 | Phase 14 | Complete |
| CHAN-01 | Phase 13 | Complete — Plans 13-01/13-02 |
| CHAN-02 | Phase 13 | Complete — Plans 13-01/13-02 |
| CHAN-03 | Phase 15 | Complete |
| PUSH-01 | Phase 16 | Complete |
| PUSH-02 | Phase 16 | Complete |
| PUSH-03 | Phase 14 | Complete |
| TGFORMAT-01 | Phase 14 | Complete |
| TGFORMAT-02 | Phase 14 | Complete |
| TGOTP-01 | Phase 17 | Complete |
| TGOTP-02 | Phase 17 | Complete |
| TGOTP-03 | Phase 17 | Complete |
| TGOTP-04 | Phase 17 | Complete |
| CMD-01 | Phase 14 | Complete |
| CMD-02 | Phase 14 | Complete |

**Coverage:**

- v3.0 requirements: 18 total
- Mapped to phases: 18 ✓
- Unmapped: 0

---
*Requirements defined: 2026-07-12*
*Last updated: 2026-07-12 after initial definition*
