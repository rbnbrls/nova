# Feature Research

**Domain:** Multi-channel household assistant (Telegram + WhatsApp)
**Researched:** 2026-07-12
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Telegram bot inbound chat (full agent-loop parity) | Core: users must be able to talk to Nova via Telegram like they do via WhatsApp | MEDIUM | Receives `message` updates via webhook → extracts `message.text` + `message.from.id` → identity resolution → `run_agent()` → `sendMessage`. Same pattern as current `process_incoming_whatsapp()` but Telegram payloads differ structurally. |
| Telegram outbound message delivery | Core: bot replies must reach the user's Telegram chat | LOW | `sendMessage` to `chat_id` (BIGINT 64-bit). 1-4096 chars. No 24h window constraint (unlike WhatsApp!). No template pre-approval needed for proactive messages. |
| Inbound identity resolution (Telegram `chat_id` → User) | Core: must know who is talking | LOW-MEDIUM | Telegram `message.chat.id` (private chat) is a stable 64-bit integer per user. Map in `user_preferences.telegram_chat_id` (BIGINT). Different DB column type than WhatsApp's TEXT phone number — needs `BIGINT` not `TEXT`. `callback_query.from.id` also gives the same chat_id for inline keyboard presses. |
| Webhook signature verification (Telegram) | Core: security parity with existing WhatsApp HMAC verification | LOW | Telegram sends `X-Telegram-Bot-Api-Secret-Token` header (set via `setWebhook(secret_token=...)`). Simpler than WhatsApp's HMAC — it's an exact string comparison. Use `hmac.compare_digest()` matching existing security pattern in `security.py`. |
| Per-user channel preferences (DB schema extension) | Core: each user chooses Telegram, WhatsApp, or both | LOW | Add columns to existing `user_preferences` table: `telegram_chat_id BIGINT UNIQUE`, `preferred_channel TEXT DEFAULT 'last_active'` (enum: `whatsapp`, `telegram`, `both`, `last_active`). Follows existing UPSERT pattern. |
| Last-active-channel tracking | Core: pushes go where the user is most recently active | LOW | Add `last_active_channel TEXT` + `last_active_at TIMESTAMPTZ` to `user_preferences`. Update on every inbound message (both channels). Read on outbound push. Pattern already partially exists — `users.last_inbound_at` is updated on WhatsApp inbound; extend to also record which channel. |
| Push gateway refactor (channel-agnostic outbound) | Core: scheduler/briefings/reminders currently hard-coded to `send_whatsapp_message()` — must route to correct channel | HIGH | **Critical refactor.** Current `scheduler.py` calls `send_whatsapp_message(number, text)` directly for ALL pushes (briefings, task reminders, email alerts, DND queue flush). Must introduce a `push_gateway.send(user_name, text, proactive=True)` function that resolves channel from `last_active_channel` / `preferred_channel` → dispatches to WhatsApp or Telegram. Also must refactor `queued_notifications` table — currently has `whatsapp_number` column hardcoded. |
| Telegram formatting for briefings/alerts | Core: existing briefings use WhatsApp `*bold*` syntax — Telegram needs HTML or MarkdownV2 | LOW | Current briefings use `*text*` for bold (WhatsApp style). Telegram: use `<b>text</b>` with `parse_mode=HTML`. Need a thin formatting adapter OR generate both formats from a common intermediate. Recommend HTML mode — far simpler escaping than MarkdownV2 (no need to escape 20+ special chars). |
| Telegram self-service OTP linking | Core: users must be able to link their Telegram account to Nova | MEDIUM | Flow: Dashboard → selects user → generates 6-digit code → bot sends code to user's Telegram chat (requires `telegram_chat_id` already known) → user confirms via inline keyboard button `[✓ Confirm]`. Differs from WhatsApp OTP where user must type the code back. Telegram's inline keyboard makes one-tap confirm possible. |
| Channel-agnostic `identity.py` extension | Core: current `user_from_whatsapp()` only handles phone numbers | LOW | Add `user_from_telegram(chat_id: int) -> User` alongside existing function. Same DB lookup pattern but on `telegram_chat_id` column. Add `get_all_telegram_users()` mirroring `get_all_whatsapp_users()`. |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Telegram streaming reply drafts (`sendMessageDraft`) | Users see Nova "thinking" in real-time — much better UX for slow LLM responses | MEDIUM | New Bot API 10.1 feature (June 2026). Send partial messages while agent loop runs, then `sendMessage` with final result. 30-second preview window. Could show "Thinking..." placeholder or streamed tokens. WhatsApp has no equivalent — this makes Telegram the premium channel. |
| Silent push notifications during DND (`disable_notification=True`) | Proactive messages arrive silently during DND instead of being queued/delayed | LOW | Telegram natively supports silent messages. Instead of queuing during DND (current WhatsApp behavior), send immediately but silently for Telegram. Per-channel DND behavior is a nice touch. |
| Telegram inline keyboards for interactive flows | Structured responses (confirm/deny, pick options) without free-text parsing | MEDIUM | `InlineKeyboardMarkup` with `callback_data` (1-64 bytes). For OTP: `[✓ Confirm code 123456]` button. For task completion: `[✓ Done] [✗ Not yet]` buttons. `CallbackQuery` update arrives → `answerCallbackQuery()` required within timeout to dismiss progress bar. Significant UX upgrade over WhatsApp's text-only interactions. |
| Deep linking for one-tap account linking | User clicks `t.me/NovaBot?start=link_<token>` from dashboard → instantly linked | LOW | Telegram deep linking: `https://t.me/bot?start=<param>` passes up to 64 chars to bot. Dashboard links encode user+token in start param → `/start link_abc123` triggers auto-linking without typing any code. Much smoother than WhatsApp's OTP flow. |
| Per-channel DND preferences | User can set different DND windows for WhatsApp vs Telegram | LOW-MEDIUM | Add `telegram_dnd_enabled`, `telegram_dnd_start`, `telegram_dnd_end` to `user_preferences`. Useful when user wants Telegram always-on but WhatsApp offline. Current single DND fields become the "global" DND. |
| Telegram bot command menu | Discoverable interface — users see available commands when typing `/` | LOW | Register commands via `setMyCommands()`: `/help`, `/settings`, `/tasks`, `/calendar`. Gives Nova a structured discoverable interface that WhatsApp can't match. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Duplicate pushes to ALL channels | "What if I miss it on one channel?" | Duplicate notifications are annoying and break trust. Creates exponential complexity when 3+ channels exist. Users quickly mute or abandon noisy assistants. | Last-active routing (single channel per push) with user override to pin a preferred channel. |
| Group chat support | "Can we have a family chat with Nova?" | Completely different message model — bot sees all messages, identity resolution becomes multi-user-per-message, privacy boundaries blur. Huge scope explosion. | Keep private-chat-only for now. Household coordination via shared task list visible in dashboard. |
| Telegram voice message transcription on inbound | "I want to talk to Nova on Telegram" | Requires Whisper pipeline integration on Telegram audio → text before agent loop. Adds significant complexity (voice format detection, silence detection, audio streaming). Voice channel already exists via ESPHome/HA. | Use existing voice channel for voice. Text-chat only on Telegram/WhatsApp for now. |
| Telegram channel (broadcast) support | "Share daily briefings in a channel" | Telegram channels are fundamentally different from private chats — different identity model, no reply capability, broadcast-only. Would require a completely separate adapter. | Bot sends briefings to personal chats on Telegram. Dashboard for shared household view. |
| MarkdownV2 parse mode for Telegram | "More formatting options" | MarkdownV2 requires escaping ~20 special characters (`_`, `*`, `[`, `]`, `(`, `)`, `~`, `` ` ``, `>`, `#`, `+`, `-`, `=`, `|`, `{`, `}`, `.`, `!`). One missed escape = API error and silent message failure. Extremely fragile. | Use HTML parse mode — only need to escape `<`, `>`, `&`. Much simpler, less error-prone, same visual result. |
| Per-message channel picker in chat | "Let me choose which channel each reply goes to" | Adds complex routing state machine inside the agent loop. Breaks the abstraction of channel-agnostic Nova Core. Confusing UX. | Channel preference is set at preference level, not per-message. Last-active routing handles the rest. |
| Telegram Login Widget for dashboard auth | "Seamless login with Telegram" | Overkill for a 2-user household dashboard. Adds complexity of Telegram Login Widget integration, domain verification, hash verification. | Dashboard stays LAN-only without auth (current model). OTP linking handles account binding. |

## Feature Dependencies

```
[Telegram Bot Webhook + Identity Resolution]
    ├──requires──> [DB schema: telegram_chat_id column]
    │                  └──requires──> [DB migration infrastructure (existing)]
    │
    ├──requires──> [Telegram Bot Token + BotFather setup]
    │
    └──requires──> [Telegram webhook security (secret_token)]
                       └──requires──> [HTTPS endpoint (existing Caddy setup)]

[Per-User Channel Preferences]
    ├──requires──> [DB schema: telegram_chat_id, preferred_channel, last_active_channel]
    └──enhances──> [Telegram Bot Identity Resolution]

[Push Gateway Refactor]
    ├──requires──> [Per-User Channel Preferences]
    ├──requires──> [Telegram outbound (sendMessage function)]
    └──requires──> [Last-Active-Channel Tracking]
         └──requires──> [Telegram Bot Inbound (updates last_active on Telegram message)]

[Telegram OTP Linking]
    ├──requires──> [Telegram Bot Identity Resolution]
    ├──requires──> [Telegram outbound (to send OTP code)]
    ├──requires──> [Inline keyboards (for confirm button)]
    └──enhances──> [Per-User Channel Preferences (populates telegram_chat_id)]

[Telegram Streaming Drafts]
    └──requires──> [Telegram Bot Inbound (needs active chat)]

[Per-Channel DND]
    └──requires──> [Push Gateway Refactor (so DND check is channel-aware)]
```

### Dependency Notes

- **Telegram Bot Inbound requires DB schema:** The `telegram_chat_id` column must exist in `user_preferences` before identity resolution can work. Add via migration in `db.py`.
- **Push Gateway requires channel preferences:** Cannot route pushes without knowing which channel to use. Channel preferences must be built first.
- **Telegram OTP enhances channel preferences:** The OTP linking flow is the mechanism by which `telegram_chat_id` gets populated for new users. Without it, users can't add Telegram.
- **Last-active tracking is bidirectional:** Both WhatsApp inbound and Telegram inbound must update `last_active_channel` + `last_active_at`. The push gateway reads this to decide routing.
- **Deep linking enhances OTP:** Deep linking (`?start=link_<token>`) is an alternative/supplement to the OTP flow — can auto-link without user typing. Lower friction but requires dashboard to generate deep links.

## MVP Definition

### Launch With (v3.0)

Minimum viable multi-channel — what's needed to validate Telegram parity.

- [ ] Telegram bot webhook inbound + identity resolution — Core chat parity
- [ ] Telegram outbound `sendMessage` — Bot must be able to reply
- [ ] Channel-agnostic formatting adapter — Briefings/alerts render correctly on both channels
- [ ] Push gateway refactor — All existing pushes route to correct channel
- [ ] Last-active-channel tracking + routing — Pushes go where user is active
- [ ] Per-user channel preferences DB schema — Foundation for all preference features
- [ ] Telegram OTP self-service linking — Users can add Telegram without admin help
- [ ] Webhook signature verification — Security parity with WhatsApp

### Add After Validation (v3.x)

Features to add once core multi-channel is working.

- [ ] Telegram inline keyboards for interactive flows — OTP confirm, task completion
- [ ] Telegram streaming reply drafts (`sendMessageDraft`) — Better UX for slow LLM
- [ ] Telegram bot command menu (`setMyCommands`) — Discoverable interface
- [ ] Deep linking for one-tap account linking — Smoother onboarding

### Future Consideration (v4+)

Features to defer until core is proven.

- [ ] Per-channel DND preferences — Nice but not essential when single-DND works
- [ ] Telegram voice message transcription — Use existing voice channel instead
- [ ] Group chat support — Major scope expansion
- [ ] Telegram channel broadcasts — Different paradigm entirely
- [ ] MarkdownV2 formatting — HTML mode covers needs without escaping nightmares

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Telegram bot inbound + identity | HIGH | MEDIUM | P1 |
| Telegram outbound sendMessage | HIGH | LOW | P1 |
| Push gateway refactor | HIGH | HIGH | P1 |
| Last-active-channel routing | HIGH | LOW | P1 |
| Per-user channel preferences DB | HIGH | LOW | P1 |
| Telegram OTP linking | HIGH | MEDIUM | P1 |
| Webhook signature verification | HIGH | LOW | P1 |
| Formatting adapter (HTML vs WhatsApp) | HIGH | LOW | P1 |
| Telegram inline keyboards (OTP confirm) | MEDIUM | LOW | P2 |
| Streaming reply drafts | MEDIUM | MEDIUM | P2 |
| Command menu | LOW | LOW | P2 |
| Deep linking for account linking | MEDIUM | LOW | P2 |
| Per-channel DND | LOW | LOW | P3 |
| Voice transcription | LOW | HIGH | P3 |
| Group chat | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for v3.0 launch
- P2: Should have, add when core is working
- P3: Nice to have, future consideration

## Telegram-Specific Behaviors (Calling Out Key Differences)

### Inbound Identity Resolution

| Aspect | WhatsApp (current) | Telegram (new) |
|--------|--------------------|-----------------|
| Identity key | Phone number (TEXT, E.164 without `+`) | `chat_id` (BIGINT 64-bit) |
| Source field | `payload.value.messages[0].from` | `update.message.chat.id` or `update.message.from.id` |
| DB column | `user_preferences.whatsapp_number TEXT` | `user_preferences.telegram_chat_id BIGINT` |
| Stability | Can change if user changes phone number | Permanent — tied to Telegram account |
| Additional info | None from webhook | `from.first_name`, `from.username`, `from.language_code` available |

### Outbound Message Constraints

| Aspect | WhatsApp | Telegram |
|--------|----------|----------|
| Proactive outside 24h | Template message only (pre-approved) | Free text! No 24h window for bots |
| Max text length | 4096 chars (same) | 4096 chars (same) |
| Formatting syntax | `*bold*`, `_italic_` (asterisks) | `<b>bold</b>` HTML or `*bold*` MarkdownV2 |
| Rate limit | Meta API limits | 30 msgs/sec free (per bot to all users) |
| Inline buttons | Interactive template buttons | `InlineKeyboardMarkup` with `callback_data` |
| Callback handling | N/A | Must call `answerCallbackQuery` promptly or user sees progress bar |
| Silent messages | Not supported | `disable_notification=True` for quiet delivery |

### Webhook Security

| Aspect | WhatsApp | Telegram |
|--------|----------|----------|
| Verification method | `X-Hub-Signature-256` HMAC-SHA256 of raw body | `X-Telegram-Bot-Api-Secret-Token` exact string match |
| Secret | `whatsapp_app_secret` (HMAC key) | `secret_token` (exact compare, A-Za-z0-9_- only, 1-256 chars) |
| Setup | Meta verifies via handshake GET | Bot calls `setWebhook(url=..., secret_token=...)` |

### OTP Flow Comparison

| Aspect | WhatsApp OTP (existing) | Telegram OTP (new) |
|--------|------------------------|---------------------|
| Code delivery | WhatsApp message to phone number | Bot `sendMessage` to `chat_id` |
| User confirmation | Type code back in dashboard text field | Tap inline button `[✓ Confirm]` OR type code in dashboard |
| Security model | Same: 6-digit, 10-min expiry, 3 attempts max | Same security params, better UX |
| Prerequisite | User has phone number in dashboard | User must have started chat with bot first (to get `chat_id`) |
| Auto-linking | Not possible | Deep link `?start=link_<token>` enables one-tap |

## Competitor Feature Analysis

| Feature | Home Assistant Notify | n8n/Make.com bots | Our Approach |
|---------|-----------------------|--------------------|--------------|
| Channel routing | Per-service notify calls (user picks) | Workflow branches per channel | Last-active automatic routing — user doesn't choose per message |
| Identity model | Per-platform user IDs, no unification | Each integration has own context | Unified User model across channels |
| Formatting | Platform-specific templates | Per-node formatting | Common text → per-channel formatter |
| Push routing | User specifies target platform per automation | Hardcoded in workflow | Automatic via last-active-channel preference |

## Sources

- [Telegram Bot API official documentation](https://core.telegram.org/bots/api) — Bot API v10.1 (June 2026)
- [Telegram Bot Features](https://core.telegram.org/bots/features) — Deep linking, keyboards, commands
- [Existing Nova codebase](services/nova-core/app/) — WhatsApp patterns, identity, scheduler, DB schema
- [PROJECT.md](.planning/PROJECT.md) — v3.0 milestone scope and constraints

---
*Feature research for: Nova v3.0 Multi-Channel Support (Telegram + WhatsApp)*
*Researched: 2026-07-12*
