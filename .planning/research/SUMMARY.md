# Project Research Summary

**Project:** Nova v3.0 Multi-Channel Support (Telegram + WhatsApp)
**Domain:** Self-hosted household assistant — adding Telegram as second chat channel alongside existing WhatsApp
**Researched:** 2026-07-12
**Confidence:** HIGH

## Executive Summary

Nova is a self-hosted, privacy-first household assistant serving two users (Ruben & Méral) via a channel-agnostic AI agent loop. v3.0 adds Telegram as a second messaging channel alongside the existing WhatsApp integration. Research confirms this is a well-scoped extension: the agent loop (`agent.py`) is already channel-agnostic, and channel coupling is confined to exactly three points — inbound parsing, outbound sending, and identity resolution. Adding Telegram means mirroring the WhatsApp adapter pattern and introducing a thin dispatch layer for outbound push routing.

The recommended stack adds a single dependency — `python-telegram-bot` v22.8 — used in "Bot-only" mode (not its full Application class, which conflicts with FastAPI's event loop). Webhooks are the correct pattern (matching WhatsApp's existing architecture), with Caddy/Coolify already handling SSL termination. The integration follows a clean 5-phase build order: schema migration → Telegram bot foundation → multi-channel identity → push gateway refactor → OTP linking.

The highest-risk work is the push gateway refactor — all 5 scheduler call sites currently hardcode WhatsApp delivery, and any regression silently breaks morning briefings, task reminders, and email alerts. Mitigation: additive-only DB migrations, a WhatsApp fallback chain, and a feature flag (`NOVA_TELEGRAM_ENABLED`). All other phases are low-to-medium risk with well-documented patterns from Telegram's official API docs and the existing Nova codebase.

## Key Findings

### Recommended Stack

One new dependency, zero new infrastructure. PTB v22.8 is the clear winner over alternatives (aiogram, telethon) because it ships an official FastAPI/Starlette webhook integration example, uses httpx internally (already in Nova's stack), and provides a built-in rate limiter.

**Core technologies:**
- **python-telegram-bot 22.8**: Telegram Bot API client — only the `Bot` class (NOT `Application`), used for outbound `send_message()` and webhook setup. Async, httpx-backed.
- **httpx 0.28.1** (existing): Outbound HTTP to Telegram Bot API — reused from WhatsApp adapter, no new HTTP client needed.
- **FastAPI 0.115.6** (existing): Telegram webhook endpoint added at `/webhooks/telegram` alongside existing `/webhooks/whatsapp`.
- **asyncpg 0.30.0** (existing): DB pool unchanged; new columns + `channel_identities` table added via additive-only migrations.
- **Docker/Coolify** (existing): No new containers — PTB Bot runs inside the nova-core process.

### Expected Features

**Must have (v3.0 launch — table stakes):**
- Telegram bot inbound chat with full agent-loop parity — users message Nova via Telegram exactly like WhatsApp
- Telegram outbound `sendMessage` — bot replies reach user's Telegram chat (no 24h window constraint, unlike WhatsApp)
- Webhook signature verification via `X-Telegram-Bot-Api-Secret-Token` — simpler than WhatsApp HMAC, constant-time comparison
- Per-user channel preferences in DB — each user chooses Telegram, WhatsApp, or both
- Last-active-channel tracking — pushes route to whichever channel the user most recently messaged from
- Push gateway refactor — scheduler/briefings/reminders route to correct channel (currently hardcoded to WhatsApp at 5 call sites)
- Telegram formatting adapter (HTML parse mode) — existing `*bold*` WhatsApp syntax → `<b>bold</b>` for Telegram
- Telegram OTP self-service linking — users link their Telegram account via dashboard-initiated verification code

**Should have (v3.x — differentiators):**
- Telegram inline keyboards for interactive flows — one-tap OTP confirm, task completion buttons
- Streaming reply drafts (`sendMessageDraft`) — real-time "thinking" indicator while LLM reasons (Telegram-exclusive UX advantage)
- Bot command menu (`setMyCommands`) — discoverable `/help`, `/tasks`, `/settings` interface
- Deep linking for one-tap account linking — `t.me/NovaBot?start=link_<token>` auto-linking

**Defer (v4+):**
- Group chat support — completely different message model, major scope explosion
- Per-channel DND preferences — nice but not essential
- Telegram voice message transcription — existing ESPHome/voice channel covers this
- Telegram channel broadcasts — different paradigm entirely
- MarkdownV2 formatting — HTML mode covers needs without escaping nightmares

### Architecture Approach

The recommended architecture introduces a `channels/` package with a `ChannelAdapter` protocol (structural typing, not base class hierarchy — appropriate for 2 channels, 2 users). Each channel is a flat module implementing two methods (`send_message`, `resolve_user`) plus channel-specific webhook parsing. A thin `Dispatcher` sits between callers (scheduler, DND queue, OTP) and adapters, resolving channel preference → correct adapter. The existing `whatsapp.py` is refactored into `channels/whatsapp.py` to conform to the adapter interface.

**Major components:**
1. **`channels/__init__.py`** — `ChannelAdapter` ABC + `InboundMessage` dataclass defining the interface
2. **`channels/whatsapp.py`** — Refactored WhatsApp adapter (existing logic, new interface)
3. **`channels/telegram.py`** — New Telegram adapter using PTB `Bot` class for outbound, manual webhook parsing for inbound
4. **`channels/dispatcher.py`** — Single outbound fan-out: resolves `user_name` → `last_active_channel` → `channel_identities` → adapter
5. **`channels/identity.py`** — Multi-channel identity resolution via `channel_identities` table (replaces `identity.py`)
6. **`channels/webhook_router.py`** — FastAPI `APIRouter` mounting `/webhooks/whatsapp` and `/webhooks/telegram` under shared prefix

**Key schema changes:**
- `user_preferences`: add `last_active_channel TEXT`, `channels_enabled TEXT[]`
- New `channel_identities` table: `(user_id, channel, channel_id)` with UNIQUE constraint
- Rename `whatsapp_verification_codes` → `channel_verification_codes`, add `channel` column
- `queued_notifications`: add `channel` column, make `whatsapp_number` nullable

### Critical Pitfalls

1. **HMAC vs secret token confusion** — Telegram uses `X-Telegram-Bot-Api-Secret-Token` (static bearer token), NOT HMAC body signing like WhatsApp. Writing `verify_telegram_secret_token()` as a separate function with `hmac.compare_digest()` prevents both silent rejections and timing attacks.

2. **Duplicate agent execution from webhook retries** — Telegram retries on non-2xx responses. Must use `processed_telegram_updates` dedup table with `update_id` as primary key and return HTTP 200 immediately, processing in background tasks.

3. **Push gateway refactoring breaks existing notifications** — All 5 scheduler call sites hardcode `send_whatsapp_message()`. Regression means silent failure of briefings/alerts. Mitigation: additive-only migrations, WhatsApp fallback chain, feature flag, run full pytest suite after every refactor.

4. **4096 character message limit breaking briefings** — WhatsApp effectively unlimited (~65k chars), Telegram caps at 4096. Busy-week briefings exceed this. Must add a message-chunking utility that splits at paragraph boundaries with 1-second delays between chunks.

5. **Cold-start state for users without Telegram** — New `last_active_channel` column defaults to WhatsApp, but push router must explicitly handle NULL `telegram_chat_id` with fallback to WhatsApp. No silent failures allowed.

## Implications for Roadmap

Based on the dependency chain discovered across all research, the work breaks into 5 clearly ordered phases:

### Phase 1: Foundation — Schema Migration + Channel Adapter Skeleton
**Rationale:** Every subsequent phase depends on DB schema changes and the adapter abstraction. The WhatsApp refactor validates the abstraction on the existing working channel before adding Telegram complexity.
**Delivers:**
- Additive-only DB migrations: `last_active_channel`, `channels_enabled` on `user_preferences`; `channel_identities` table; rename `whatsapp_verification_codes` → `channel_verification_codes`
- `channels/` package with `ChannelAdapter` protocol, `InboundMessage` dataclass
- WhatsApp refactored into `channels/whatsapp.py` conforming to adapter interface
- Webhook APIRouter extracting routes from `main.py`
**Addresses:** Channel-agnostic identity resolution foundation, per-user channel preferences DB schema
**Avoids:** Pitfall #4 (cold-start) — additive-only migrations ensure existing WhatsApp path unaffected
**Research flags:** Standard patterns — well-documented DB migrations + code refactoring. No research-phase needed.

### Phase 2: Telegram Bot Foundation — Inbound/Outbound Chat Parity
**Rationale:** With the adapter skeleton validated on WhatsApp, adding the Telegram adapter is mechanical. This phase delivers the core value — users can chat with Nova via Telegram.
**Delivers:**
- `channels/telegram.py`: TelegramAdapter with PTB `Bot` class init/shutdown in lifespan
- `POST /webhooks/telegram` endpoint with `X-Telegram-Bot-Api-Secret-Token` verification
- `processed_telegram_updates` dedup table for retry protection
- Full inbound→agent→outbound loop verified end-to-end
- Config additions: `telegram_bot_token`, `telegram_bot_secret_token`, `public_base_url`
**Uses:** python-telegram-bot 22.8 (Bot class only), httpx, FastAPI lifespan
**Implements:** `channels/telegram.py` adapter, webhook security via `verify_telegram_secret_token()`
**Avoids:** Pitfall #1 (HMAC vs secret_token — separate verification function), Pitfall #2 (webhook retries — dedup table), Pitfall #6 (BIGINT for chat_id)
**Research flags:** Standard patterns — PTB webhook integration follows official `customwebhookbot` example. No research-phase needed.

### Phase 3: Multi-Channel Identity + Last-Active Tracking
**Rationale:** Identity resolution must work for both channels before the push dispatcher can route correctly. Last-active tracking is the single source of truth for outbound routing decisions.
**Delivers:**
- `channels/identity.py`: `resolve_user(channel, channel_id)` using `channel_identities` table
- Both webhook handlers update `last_active_channel` + `last_inbound_at` atomically on every inbound message
- Deprecated `identity.py` WhatsApp-only functions redirect to new multi-channel resolver
**Implements:** `channels/identity.py`, atomic last-active UPDATE pattern
**Avoids:** Pitfall #2 (race conditions — single atomic UPDATE for both `last_inbound_at` and `last_active_channel`)
**Research flags:** Standard patterns — straightforward DB lookup + atomic UPDATE. No research-phase needed.

### Phase 4: Push Gateway Refactor — Channel-Agnostic Outbound
**Rationale:** This is the highest-risk phase and must come after identity + last-active tracking are solid. It refactors all 5 scheduler call sites from hardcoded WhatsApp to dispatcher-based routing. Must be done carefully with regression protection.
**Delivers:**
- `channels/dispatcher.py`: `send_to_user(user_name, text)` with channel resolution + DND queue logic
- All 5 scheduler call sites refactored from `send_whatsapp_message()` to `dispatcher.send_to_user()`
- `queued_notifications` table generalized (add `channel` column, `whatsapp_number` nullable)
- Message chunking utility for Telegram's 4096-char limit
- HTML formatting adapter for briefings (WhatsApp `*bold*` → Telegram `<b>bold</b>`)
**Addresses:** Push gateway refactor, Telegram formatting, last-active-channel routing
**Avoids:** Pitfall #3 (push failures — WhatsApp fallback chain + feature flag), Pitfall #4 (silent push failures — explicit channel resolution with fallback), Pitfall #5 (4096 char limit — chunking utility), Pitfall #10 (queued_notifications migration — additive approach)
**Research flags:** **NEEDS RESEARCH-PHASE** — This is the highest-risk refactor. 5 call sites must be migrated without breaking any existing notification path. Phase planning should deeply inspect each call site's current behavior to ensure equivalence.

### Phase 5: Telegram OTP Self-Service Linking
**Rationale:** OTP linking is the mechanism by which users add Telegram to their profile. It depends on a working Telegram bot (Phase 2) and the multi-channel identity system (Phase 3), but is independent of the push gateway (Phase 4) — can theoretically run in parallel.
**Delivers:**
- Dashboard endpoint: `POST /api/preferences/request-telegram-code` (separate from WhatsApp endpoint)
- Bot delivers 6-digit OTP code to user's Telegram chat
- Dashboard endpoint: `POST /api/preferences/verify-telegram-code`
- Writes to `channel_identities` + updates `channels_enabled`
- Inline keyboard confirm button for one-tap verification (if time permits)
**Implements:** Telegram OTP flow using `channel_verification_codes` table
**Avoids:** Pitfall #8 (bot-to-bot testing trap — test from real Telegram accounts only), Pitfall #9 (privacy mode — private chat only, reject group messages)
**Research flags:** Standard patterns — OTP flow mirrors existing WhatsApp implementation. No research-phase needed.

### Phase Ordering Rationale

- **Phase 1 first** — Schema changes are the foundation everything else builds on. Refactoring WhatsApp into the adapter pattern validates the abstraction before adding Telegram complexity.
- **Phase 2 before Phase 3** — Telegram bot must be working before identity resolution needs to handle it.
- **Phase 3 before Phase 4** — The dispatcher needs identity resolution and last-active tracking to route correctly. Routing without identity = guessing.
- **Phase 4 is the riskiest** — Saved for after the foundation is solid. Feature flag + WhatsApp fallback provide rollback safety.
- **Phase 5 can parallel Phase 4** — OTP is a separate flow from proactive push, with different dependencies.

### Research Flags

**Needs research during planning:**
- **Phase 4 (Push Gateway Refactor):** Highest risk. 5 scheduler call sites must be migrated without breaking briefings, task reminders, email alerts, or DND queue flush. Each call site needs careful inspection of current behavior to ensure dispatcher equivalence. Consider `--research-phase` during planning.

**Standard patterns (skip research-phase):**
- **Phase 1 (Schema + Adapter Skeleton):** Well-documented DB migrations + code refactoring. Existing codebase provides clear patterns.
- **Phase 2 (Telegram Bot):** PTB v22.8 official docs + `customwebhookbot` example provide exact integration pattern. Webhook security (secret_token) is documented in Telegram Bot API reference.
- **Phase 3 (Multi-Channel Identity):** Straightforward DB lookups and atomic updates. Existing `identity.py` pattern transfers directly.
- **Phase 5 (Telegram OTP):** Mirrors existing WhatsApp OTP flow. Same 6-digit code + verification pattern, different delivery channel.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Official PTB v22.8 docs, Telegram Bot API reference, and existing codebase analysis all converge. No ambiguity on library choice or integration pattern. |
| Features | HIGH | Feature set derived from direct codebase analysis + Telegram API capabilities. Clear table-stakes vs differentiator separation. Anti-features well-justified. |
| Architecture | HIGH | Channel coupling analyzed at 3 specific points in codebase. Adapter pattern appropriate for scale (2 channels, 2 users). Schema design analyzed against existing tables. |
| Pitfalls | HIGH | Top 5 critical pitfalls identified from official Telegram API docs + codebase patterns. Prevention strategies verified against documented behavior. |

**Overall confidence:** HIGH

### Gaps to Address

- **`channel_identities` backfill strategy:** The migration plan mentions programmatically backfilling from existing `whatsapp_number` data but doesn't detail the exact backfill script. Validate during Phase 1 planning.
- **Telegram `chat_id` format in `channel_identities`:** The table stores `channel_id` as TEXT. Need to confirm that casting Telegram's BIGINT chat_id to string and back is lossless for values up to 52 significant bits. Validate with a real Telegram user's chat_id during Phase 2.
- **Briefing length in production:** We don't know how often real briefings exceed 4096 chars. Monitor after Phase 4 launch to see if chunking is needed frequently or edge-case-only.
- **`python-telegram-bot` v22.8 compatibility with existing httpx version:** PTB uses httpx internally. Nova has httpx 0.28.1. Confirm no version conflict during Phase 2 implementation.

## Sources

### Primary (HIGH confidence)
- [Telegram Bot API official docs](https://core.telegram.org/bots/api) (v10.1, June 2026) — setWebhook secret_token, sendMessage limits (4096 chars), chat.id 64-bit warning, update_id semantics
- [python-telegram-bot v22.8 docs](https://docs.python-telegram-bot.org/en/stable/) — Bot class, HTTPXRequest, Application lifecycle, customwebhookbot pattern
- [Telegram Webhook Guide](https://core.telegram.org/bots/webhooks) — SSL termination, ports, security model
- Direct codebase analysis of `services/nova-core/app/` — all files (main.py, whatsapp.py, security.py, identity.py, scheduler.py, db.py)

### Secondary (MEDIUM confidence)
- [PTB Wiki: Webhooks](https://github.com/python-telegram-bot/python-telegram-bot/wiki/Webhooks) — custom integration patterns with reverse proxy
- [PTB Wiki: Design Patterns](https://github.com/python-telegram-bot/python-telegram-bot/wiki) — Running PTB alongside other asyncio frameworks
- aiogram 3.x docs — considered and rejected (lacks official FastAPI/Starlette examples)

### Tertiary (LOW confidence)
- Telegram broadcast rate limits (30 msgs/sec) — from FAQ, not directly tested at Nova's scale
- `update_id` sequence reset behavior after inactivity — from official docs but edge-case, not tested empirically

---
*Research completed: 2026-07-12*
*Ready for roadmap: yes*
