# Technology Stack: Telegram Multi-Channel Support

**Project:** Nova v3.0 Multi-Channel Support
**Researched:** 2026-07-12
**Focus:** Stack additions/changes for Telegram alongside existing WhatsApp

## Recommended Stack

### Core Addition: Telegram Bot Library

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| python-telegram-bot | 22.8 | Telegram Bot API client + handler framework | Largest Python Telegram library (29.3k stars), official FastAPI/Starlette webhook examples, fully async since v20, uses httpx internally (already in Nova's stack) |
| httpx | 0.28.1 (already present) | Outbound HTTP to Telegram Bot API for sending replies | Already used by WhatsApp adapter + PTB's internal HTTPXRequest. No new dep needed. |

**Why python-telegram-bot (PTB) over alternatives:**
- Official `customwebhookbot.py` example demonstrates Starlette/uvicorn integration — directly maps to Nova's FastAPI architecture
- Supports the exact integration pattern Nova needs: `Application.builder().token(TOKEN).updater(None).build()` with manual `update_queue` feeding from existing FastAPI routes
- `AIORateLimiter` built-in for Telegram API rate limits (~30 msgs/sec, ~20 msgs/min per chat)
- `JobQueue` (APScheduler-backed) could later complement Nova's existing scheduler for Telegram-specific jobs
- Alternatives (`aiogram`, `telethon`) were considered and rejected — see Alternatives section

### What Does NOT Change

| Component | Current | Notes |
|-----------|---------|-------|
| FastAPI | 0.115.6 | Telegram webhook endpoints added alongside existing `/webhooks/whatsapp` |
| uvicorn | 0.34.0 | No change — PTB runs in "no updater" mode, doesn't start its own server |
| httpx | 0.28.1 | Reused for outbound Telegram API calls (same pattern as `whatsapp.py`) |
| asyncpg | 0.30.0 | DB pool unchanged; new migrations for Telegram columns |
| Docker/Coolify | existing | No new containers needed — PTB runs inside nova-core process |

### Webhook Architecture Decision

**Use webhooks (not polling) — webhook is the correct choice for Nova.**

| Factor | Webhooks | Polling |
|--------|----------|---------|
| Latency | Instant (~ms from Telegram) | 1-5 sec delay per poll cycle |
| Resource usage | Push-based, idle until message arrives | Constant CPU/network even with 0 messages |
| Matches existing pattern | Yes — WhatsApp already uses webhooks at `/webhooks/whatsapp` | No — would be novel pattern |
| Coolify/Traefik ingress | Already handles reverse proxy + SSL termination | N/A — polling doesn't need ingress |
| PTB recommendation | Recommended for production bots behind reverse proxy | "Fine for smaller bots and testing" |

**Coolify integration:** Caddy already does SSL termination for `nova.local`. The webhook URL will be exposed via the same Cloudflare Tunnel path that serves WhatsApp webhooks (`/webhooks/telegram`). No additional proxy config needed — just add a new route.

**SSL:** Telegram requires HTTPS for webhooks. Caddy (via Coolify's Traefik) already handles SSL termination. PTB's `customwebhookbot` pattern does **not** need to manage certificates — Caddy handles TLS, PTB receives plain HTTP behind the proxy.

### Webhook Security: Telegram vs WhatsApp

| Aspect | WhatsApp (existing) | Telegram (new) |
|--------|---------------------|----------------|
| Verification method | HMAC-SHA256 of raw body via `X-Hub-Signature-256` header | Direct secret token match via `X-Telegram-Bot-Api-Secret-Token` header |
| Secret source | `WHATSAPP_APP_SECRET` from Meta developer portal | `TELEGRAM_WEBHOOK_SECRET` set by you during `setWebhook()` |
| Implementation | `hmac.new()` + `hashlib.sha256` + `compare_digest` | Simple `hmac.compare_digest(request.headers["X-Telegram-Bot-Api-Secret-Token"], settings.telegram_webhook_secret)` |
| Complexity | Requires raw body capture + HMAC computation | Simpler — just a string comparison using constant-time compare |

**Key insight:** Telegram's `secret_token` is set by YOU when calling `bot.set_webhook(secret_token=...)`. Telegram echoes it in every webhook POST. You verify with a simple constant-time string comparison — no HMAC computation needed. This is simpler than WhatsApp but equally secure.

**Integration with existing `security.py`:** Add a `verify_telegram_secret_token()` function alongside the existing `verify_whatsapp_signature()`. Both use `hmac.compare_digest` for timing-safe comparison.

### Connection Pooling for Telegram Bot API

PTB's `HTTPXRequest` manages its own internal `httpx.AsyncClient` with:
- Default `connection_pool_size=256` (changed from 1 to 256 in v22.4)
- Configurable timeouts: `read_timeout=5.0`, `write_timeout=5.0`, `connect_timeout=5.0`, `pool_timeout=1.0`
- Optional HTTP/2 support (`http_version="2"`)

**For Nova's 2-user household:** The default pool size of 256 is massively overprovisioned but harmless. No tuning needed. PTB reuses connections via httpx's connection pooling — no additional pooling configuration required.

**Note:** The existing WhatsApp code in `whatsapp.py` creates a fresh `httpx.AsyncClient()` per request (`async with httpx.AsyncClient() as client`). This is inefficient. As part of the Telegram phase, consider refactoring to share a single `httpx.AsyncClient` across both channels (managed via FastAPI lifespan) — though this is an optimization, not a blocker.

### asyncio Compatibility

**Fully compatible.** PTB v20+ is 100% coroutine-based. The critical integration point is the FastAPI lifespan:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... existing DB init, scheduler start ...
    
    # Initialize PTB Application (Telegram)
    tg_app = Application.builder().token(settings.telegram_bot_token).updater(None).build()
    await tg_app.initialize()
    await tg_app.start()
    
    yield
    
    # Shutdown
    await tg_app.stop()
    await tg_app.shutdown()
    # ... existing scheduler, pool cleanup ...
```

**Update processing flow (matches PTB's official pattern):**
```python
@app.post("/webhooks/telegram")
async def telegram_webhook(request: Request):
    body = await request.body()  # raw body for signature check
    # verify X-Telegram-Bot-Api-Secret-Token header
    data = await request.json()
    update = Update.de_json(data=data, bot=tg_app.bot)
    await tg_app.update_queue.put(update)
    await tg_app.process_update(update)
    return Response(status_code=200)
```

**Key:** Using `updater(None)` means PTB does NOT manage its own event loop. Updates are fed from FastAPI's request handler, then dispatched through PTB's handler pipeline. The agent loop (`run_agent`) is called from within handler callbacks — same async event loop as everything else.

## New Environment Variables

```
# Telegram Bot (v3.0 Multi-Channel)
TELEGRAM_BOT_TOKEN=           # From @BotFather — e.g. "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
TELEGRAM_WEBHOOK_SECRET=      # Custom secret for X-Telegram-Bot-Api-Secret-Token (set by you)
TELEGRAM_WEBHOOK_URL=         # Public URL: e.g. "https://nova.yourdomain.com/webhooks/telegram"
```

**Config additions in `config.py`:**
```python
telegram_bot_token: str = ""
telegram_webhook_secret: str = ""
telegram_webhook_url: str = ""
```

**Coolify secrets:** All three must be added as environment secrets in Coolify, just like the WhatsApp credentials.

## Installation

```bash
# Add to requirements.txt
python-telegram-bot==22.8

# No additional extras needed for basic webhook mode
# Optional (if future voice/image support): pip install "python-telegram-bot[crypt]"
```

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Telegram library | python-telegram-bot 22.8 | aiogram 3.x | aiogram is also async and capable, but lacks official FastAPI/Starlette webhook examples. PTB's `customwebhookbot` example is the exact pattern Nova needs. PTB's built-in `AIORateLimiter` and `JobQueue` are bonuses. |
| Telegram library | python-telegram-bot 22.8 | telethon / pyrogram | Client libraries (MTProto), not Bot API. Require user account auth, not suitable for a bot. Overkill complexity. |
| Update mode | Webhooks | Long polling | Would require PTB to manage its own event loop, conflicting with FastAPI's uvicorn. Polling adds ~1s latency and constant network traffic. Webhooks match the existing WhatsApp pattern. |
| Outbound HTTP | httpx (PTB internal + reuse existing) | aiohttp | Would add a second HTTP client to the stack. httpx is already used for WhatsApp and PTB uses it internally. Consistency wins. |
| Webhook security | Telegram secret_token | Self-signed cert approach | Deprecated complexity. PTB supports certs but Caddy/Coolify handles TLS. Telegram's secret_token is simpler and recommended. |
| Library scope | PTB (full) | Raw Bot API calls via httpx | Could call `api.telegram.org/bot<token>/sendMessage` directly with httpx — but this reinvents the handler pipeline, rate limiting, and type wrappers that PTB provides for free. Not worth it. |

## Integration Points with Existing Code

### 1. New file: `app/telegram.py`
Mirror of `app/whatsapp.py` pattern:
- `send_telegram_message(chat_id: int, text: str)` — outbound via `tg_app.bot.send_message()`
- `process_incoming_telegram(update: Update)` — resolve user from Telegram user ID, call `run_agent`, reply

### 2. Modified: `app/main.py`
- Add `POST /webhooks/telegram` endpoint alongside existing `POST /webhooks/whatsapp`
- Initialize PTB Application in lifespan context manager
- Register Telegram Bot command handler for `/start`

### 3. Modified: `app/identity.py`
- Add `user_from_telegram(telegram_user_id: int) -> User` — resolves via DB lookup (telegram_user_id → user)
- Extend `get_all_users()` to include Telegram channel mappings

### 4. Modified: `app/db.py`
- Migration: add `telegram_user_id` column to `user_preferences`
- Migration: add `telegram_verification_codes` table (parallel to `whatsapp_verification_codes`)
- Migration: add `last_active_channel` column to `user_preferences`

### 5. Modified: `app/config.py`
- Add `telegram_bot_token`, `telegram_webhook_secret`, `telegram_webhook_url` settings

### 6. Modified: `app/security.py`
- Add `verify_telegram_secret_token(secret_header: str | None, expected: str) -> bool`

### 7. Modified: `Caddyfile`
- No changes needed — the existing `/webhooks/*` path pattern (via Cloudflare Tunnel) will naturally include `/webhooks/telegram`

## What NOT to Add

| Anti-Pattern | Why Avoid |
|--------------|-----------|
| PTB `run_webhook()` / `run_polling()` | These block the asyncio event loop. Nova must use the `initialize()/start()/stop()/shutdown()` pattern from the custom webhook example |
| Self-signed SSL certificates | Caddy/Coolify already handles TLS termination. Adding certs to PTB is redundant complexity |
| Separate Docker container for Telegram | PTB runs in-process with FastAPI. A separate container would require IPC and add deployment complexity for zero benefit |
| aiohttp or requests for outgoing API calls | PTB uses httpx internally. Adding another HTTP client creates connection pool fragmentation and inconsistent behavior |
| Raw Bot API calls (bypassing PTB) | Reinvents typing, rate limiting, error handling. Use PTB's `Bot.send_message()` etc. |
| A separate FastAPI app | Add webhook endpoints to the existing `app/main.py`. The agent loop, DB pool, scheduler — all shared. No isolation benefit for a 2-user household |

## Sources

- PTB official docs v22.8 (docs.python-telegram-bot.org) — Application, HTTPXRequest, customwebhookbot example — **HIGH confidence**
- Telegram Bot API reference (core.telegram.org/bots/api) — setWebhook secret_token, webhook ports, update model — **HIGH confidence**
- PTB Wiki: Webhooks page (github.com/python-telegram-bot/python-telegram-bot/wiki/Webhooks) — custom integration patterns, reverse proxy setup — **MEDIUM confidence**
- PTB Wiki: Frequently requested design patterns — Running PTB alongside other asyncio frameworks — **MEDIUM confidence**
- Existing Nova codebase analysis (main.py, whatsapp.py, security.py, config.py, db.py, Caddyfile, docker-compose.yml) — integration points verified against current code — **HIGH confidence**
