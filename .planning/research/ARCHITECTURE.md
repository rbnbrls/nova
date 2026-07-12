# Architecture Patterns: Multi-Channel Support

**Domain:** Private household assistant — adding Telegram as second chat channel
**Researched:** 2026-07-12
**Overall Confidence:** HIGH (direct codebase analysis + verified Telegram Bot API docs)

---

## Recommended Architecture

### High-Level Change

Nova's agent loop (`agent.py`) is already channel-agnostic — it takes `user_message: str` and `user: str` and returns a text reply. The channel coupling lives in exactly three places:

1. **Inbound parsing** — `whatsapp.py:process_incoming_whatsapp()` and `main.py` webhook routes
2. **Outbound sending** — `whatsapp.py:send_whatsapp_message()` called from 5 sites
3. **Identity resolution** — `identity.py:user_from_whatsapp()` / `get_all_whatsapp_users()`

Multi-channel support means: (a) add a Telegram adapter mirroring the WhatsApp one, (b) insert a thin dispatch layer between callers and adapters, (c) generalize identity resolution to cover both channels.

```
                          ┌─────────────────┐
                          │   Nova Core      │
                          │   (agent.py)     │
                          │   channel-       │
                          │   agnostic       │
                          └────────┬─────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
              ┌─────▼─────┐  ┌────▼─────┐  ┌─────▼──────┐
              │ Dispatcher │  │ Identity │  │  Push      │
              │ (channels/ │  │ Resolver │  │  Gateway   │
              │ dispatcher)│  │ (multi-  │  │ (channels/ │
              │            │  │ channel) │  │  dispatch) │
              └──────┬─────┘  └────┬─────┘  └─────┬──────┘
                     │              │              │
              ┌──────┴──────┐       │       ┌──────┴──────┐
              │  WhatsApp    │       │       │  Telegram   │
              │  Adapter     │       │       │  Adapter    │
              │ (whatsapp.py │       │       │ (telegram.py│
              │  refactored) │       │       │  new)       │
              └──────────────┘       │       └─────────────┘
                                     │
                              ┌──────▼──────┐
                              │  Postgres   │
                              │  channel_   │
                              │  identities │
                              │  + prefs    │
                              └─────────────┘
```

---

## 1. Channel Abstraction Layer

### Recommendation: Protocol-based adapter with flat modules

Create a `channels/` package alongside the existing app modules. Each channel remains a **flat module** (matching the existing `whatsapp.py` style) but conforms to a shared `ChannelAdapter` protocol.

**Why not a base class hierarchy?** The project has two channels, two users, and no need for dynamic polymorphism. A Protocol (structural typing) gives compile-time clarity without forcing artificial inheritance. If a third channel arrives later, it's one new module — not a subclass tree.

**Why not independent handlers?** The WhatsApp handler already duplicates logic that Telegram will need (identity resolution, DND check, agent call, message send). A shared protocol + dispatcher eliminates this duplication cleanly.

```python
# app/channels/__init__.py
from __future__ import annotations
import abc
from dataclasses import dataclass

@dataclass(frozen=True)
class InboundMessage:
    """Normalized input from any channel."""
    user_name: str          # resolved: "Ruben", "Meral", or "household"
    text: str
    channel: str            # "whatsapp" | "telegram"
    channel_id: str         # origin-specific: phone number or Telegram chat_id

class ChannelAdapter(abc.ABC):
    """Minimal interface every channel must implement."""

    @abc.abstractmethod
    async def send_message(self, channel_id: str, text: str, *, proactive: bool = False) -> None:
        """Send a text message to a user on this channel."""
        ...

    @abc.abstractmethod
    async def resolve_user(self, channel_id: str) -> str:
        """Map a channel-specific sender ID to a household user name."""
        ...
```

```python
# app/channels/whatsapp.py  (REFACTORED from app/whatsapp.py)
class WhatsAppAdapter(ChannelAdapter):
    async def send_message(self, channel_id: str, text: str, *, proactive: bool = False) -> None:
        # ...existing send_whatsapp_message logic...

    async def resolve_user(self, channel_id: str) -> str:
        # ...existing user_from_whatsapp logic...

    async def process_incoming(self, payload: dict) -> None:
        # ...existing process_incoming_whatsapp logic, using self.send_message...
```

```python
# app/channels/telegram.py  (NEW)
class TelegramAdapter(ChannelAdapter):
    async def send_message(self, channel_id: str, text: str, *, proactive: bool = False) -> None:
        # Use self._bot.send_message(chat_id=int(channel_id), text=text)

    async def resolve_user(self, channel_id: str) -> str:
        # Query channel_identities by channel='telegram', channel_id=chat_id

    async def process_incoming(self, update: dict) -> None:
        # Parse Update.message, resolve user, call agent, send reply
```

### Component Boundaries

| Component | Responsibility | New vs Modified | Communicates With |
|-----------|---------------|-----------------|-------------------|
| `channels/__init__.py` | `ChannelAdapter` ABC + `InboundMessage` dataclass | **NEW** | All adapters |
| `channels/whatsapp.py` | WhatsApp inbound parsing + outbound via Meta API | **MODIFIED** (refactored from `whatsapp.py`) | Meta Cloud API, identity resolver |
| `channels/telegram.py` | Telegram inbound parsing + outbound via Bot API | **NEW** | Telegram Bot API, identity resolver |
| `channels/dispatcher.py` | Outbound gateway: resolve channel → delegate to adapter | **NEW** | Scheduler, DND queue, OTP sender |
| `channels/identity.py` | Multi-channel identity resolution (replaces `identity.py`) | **NEW** (supersedes `identity.py`) | Postgres `channel_identities` table |
| `identity.py` | Legacy WhatsApp-only identity (kept for backward compat) | **DEPRECATED** | — |

### Data Flow — Inbound

```
POST /webhooks/telegram
  → verify X-Telegram-Bot-Api-Secret-Token header
  → parse Update JSON
  → extract message.from.id (int64), message.text
  → identity.resolve("telegram", str(chat_id)) → user name
  → UPDATE users SET last_inbound_at = now()
  → UPDATE user_preferences SET last_active_channel = 'telegram' WHERE user_id = ...
  → run_agent(text, user=user_name)
  → telegram_adapter.send_message(str(chat_id), reply)
```

### Data Flow — Outbound (Scheduler → User)

```
scheduler.run_briefing_scheduler()
  → query user_preferences WHERE morning_briefing_enabled = true
  → for each user:
      → dispatcher.send_proactive(user_name, text)
          → query user_preferences.last_active_channel (or fallback to whatsapp)
          → query channel_identities WHERE user_id=... AND channel=last_active
          → adapter = get_adapter(last_active)
          → adapter.send_message(channel_id, text, proactive=True)
```

---

## 2. Outbound Push Gateway (Dispatcher)

### Recommendation: Thin dispatcher that replaces direct `send_whatsapp_message` calls

The scheduler currently has **5 call sites** that directly import `send_whatsapp_message`. Refactor them through a `dispatcher.py` that:

1. Accepts `(user_name, text, *, proactive)` instead of `(number, text, *, proactive)`
2. Looks up `last_active_channel` from `user_preferences`
3. Looks up the channel-specific ID from `channel_identities`
4. Delegates to the correct adapter
5. Handles DND queuing (currently in `whatsapp.py` — move to dispatcher)

```python
# app/channels/dispatcher.py
ADAPTERS: dict[str, ChannelAdapter] = {}

async def send_to_user(user_name: str, text: str, *, proactive: bool = False) -> None:
    """Route a message to the user's last-active channel."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT up.last_active_channel, ci.channel, ci.channel_id
            FROM user_preferences up
            JOIN users u ON up.user_id = u.id
            LEFT JOIN channel_identities ci ON ci.user_id = u.id
              AND ci.channel = COALESCE(up.last_active_channel, 'whatsapp')
            WHERE u.name = $1
        """, user_name)

    if not row or not row["channel_id"]:
        # Fallback: try WhatsApp if available
        # If no channel at all, log warning and return
        return

    # DND check (moved from whatsapp.py)
    if proactive and await is_user_in_dnd(user_name):
        await _queue_notification(row["channel"], row["channel_id"], text)
        return

    adapter = ADAPTERS[row["channel"]]
    await adapter.send_message(row["channel_id"], text, proactive=proactive)

async def send_to_channel(channel: str, channel_id: str, text: str) -> None:
    """Send directly to a specific channel (used for OTP, explicit sends)."""
    adapter = ADAPTERS[channel]
    await adapter.send_message(channel_id, text)
```

### Call Sites That Must Change

| Site | Current Code | New Code |
|------|-------------|----------|
| `scheduler.py:86` | `send_whatsapp_message(number, briefing, proactive=True)` | `dispatcher.send_to_user(username, briefing, proactive=True)` |
| `scheduler.py:161` | `send_whatsapp_message(number, briefing, proactive=True)` | `dispatcher.send_to_user(username, briefing, proactive=True)` |
| `scheduler.py:244` | `send_whatsapp_message(number, alert, proactive=True)` | `dispatcher.send_to_user(assignee_name, alert, proactive=True)` |
| `scheduler.py:285` | `send_whatsapp_message(number, alert, proactive=True)` | `dispatcher.send_to_user(...)` (for each in household) |
| `scheduler.py:313` | `send_whatsapp_message(number, msg_text, proactive=False)` | `dispatcher.send_to_user(name, msg_text)` |
| `main.py:290` (OTP) | `send_whatsapp_message(number, otp_message)` | `dispatcher.send_to_channel("whatsapp", number, otp_message)` |

---

## 3. Schema Changes

### Recommendation: Add columns to existing tables + two new tables

**Do NOT create a new preferences table.** The existing `user_preferences` table is one-row-per-user — just add columns. This avoids migration complexity and keeps all user settings in one query path.

### Migration Plan

```sql
-- Phase A: Add channel columns to existing user_preferences
ALTER TABLE user_preferences
  ADD COLUMN IF NOT EXISTS last_active_channel TEXT DEFAULT 'whatsapp',
  ADD COLUMN IF NOT EXISTS channels_enabled TEXT[] DEFAULT '{whatsapp}';

-- Phase B: Create channel_identities table (maps user ↔ channel-specific IDs)
CREATE TABLE IF NOT EXISTS channel_identities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel TEXT NOT NULL,          -- 'whatsapp' | 'telegram'
    channel_id TEXT NOT NULL,       -- E.164 number or Telegram chat_id (bigint as string)
    verified_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(channel, channel_id)
);

-- Phase C: Migrate existing whatsapp_number into channel_identities
-- (done programmatically in run_migrations after table creation)

-- Phase D: Generalize verification_codes table
ALTER TABLE whatsapp_verification_codes RENAME TO channel_verification_codes;
ALTER TABLE channel_verification_codes
  ADD COLUMN IF NOT EXISTS channel TEXT DEFAULT 'whatsapp',
  ADD COLUMN IF NOT EXISTS channel_id TEXT DEFAULT '';
  -- whatsapp_number is retained for backward compat, channel_id mirrors it
```

### Table Design Rationale

| Change | Why |
|--------|-----|
| `last_active_channel` on `user_preferences` | Single-column lookup for dispatcher; updated atomically on every inbound message |
| `channels_enabled` on `user_preferences` | Array tracks which channels are linked (for UI/dashboard); set-managed by dashboard |
| New `channel_identities` table | Each channel has a different identity format (phone vs. chat_id). Separate table = clean N-channel support without N columns |
| Rename `whatsapp_verification_codes` → `channel_verification_codes` | Telegram OTP uses the same flow. Adding a `channel` column generalizes without breaking existing data |
| `UNIQUE(channel, channel_id)` | Prevents two users claiming the same Telegram chat |

### Why not separate `telegram_preferences` table?

- Fragments queries — dispatcher would need LEFT JOIN across N tables
- DND, briefing settings, and channel routing are all per-user, not per-channel
- The only channel-specific data is `channel_id` (phone/chat_id), which belongs in `channel_identities`

### Atomicity Considerations

- **Identity resolution reads** (`SELECT from channel_identities`) should use the same connection pool as the rest of the app — already the case with asyncpg
- **`last_active_channel` update** should happen in the same transaction as `last_inbound_at` update, or piggyback on it:
  ```sql
  UPDATE users SET last_inbound_at = now() WHERE name = $1;
  UPDATE user_preferences SET last_active_channel = $2
  WHERE user_id = (SELECT id FROM users WHERE name = $1);
  ```
  These can be two separate statements in the same connection — no transaction needed for atomicity of tracking (worst case: one update lags by a message).

---

## 4. FastAPI Webhook Routing

### Recommendation: Separate route files mounted via APIRouter, under shared `/webhooks/` prefix

```python
# app/channels/webhook_router.py  (NEW)
from fastapi import APIRouter

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# WhatsApp routes (moved from main.py)
@router.get("/whatsapp")
async def whatsapp_handshake(...): ...

@router.post("/whatsapp")
async def whatsapp_webhook(...): ...

# Telegram routes (NEW)
@router.post("/telegram")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    body = await request.body()
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(secret, settings.telegram_bot_secret_token):
        raise HTTPException(status_code=401, detail="Invalid secret token")
    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    background_tasks.add_task(telegram_adapter.process_incoming, payload)
    return {"status": "accepted"}
```

```python
# In main.py, replace inline webhook routes with:
from .channels.webhook_router import router as webhook_router
app.include_router(webhook_router)
```

### Path Structure

| Route | Purpose | Auth |
|-------|---------|------|
| `GET /webhooks/whatsapp` | Meta verification handshake | `hub.verify_token` query param |
| `POST /webhooks/whatsapp` | Meta webhook delivery | `X-Hub-Signature-256` HMAC header |
| `POST /webhooks/telegram` | Telegram webhook delivery | `X-Telegram-Bot-Api-Secret-Token` header (plain token) |

### Why APIRouter over inline routes?

- Keeps `main.py` from growing further (currently 434 lines, most of which is webhook + preferences)
- Each webhook handler lives alongside its adapter module
- Adding voice or a future channel = one more route file, zero changes to `main.py`

### Telegram Webhook Setup

On app startup (in lifespan), call `bot.set_webhook()`:

```python
async def lifespan(app: FastAPI):
    await db.get_pool()
    await db.run_migrations()
    # ... scheduler setup ...

    # Initialize Telegram Bot
    if settings.telegram_bot_token:
        from .channels.telegram import init_telegram
        await init_telegram()  # Creates Bot, sets webhook, registers adapter

    yield

    if settings.telegram_bot_token:
        from .channels.telegram import shutdown_telegram
        await shutdown_telegram()  # Closes Bot session

    scheduler.shutdown()
    await db.close_pool()
```

---

## 5. Telegram Bot Connection Management

### Recommendation: Module-level singleton Bot, no python-telegram-bot Application class

**Use `python-telegram-bot` library (v22.x)** for outbound calls only (`Bot.send_message()`). Do NOT use its `Application` class — it manages its own asyncio event loop, conflicting with FastAPI's lifespan.

```python
# app/channels/telegram.py
from telegram import Bot
from telegram.request import HTTPXRequest

_bot: Bot | None = None

async def init_telegram():
    global _bot
    request = HTTPXRequest(httpx_kwargs={"timeout": 10})
    _bot = Bot(
        token=settings.telegram_bot_token,
        request=request,
    )
    async with _bot:
        await _bot.set_webhook(
            url=f"{settings.public_base_url}/webhooks/telegram",
            secret_token=settings.telegram_bot_secret_token,
            allowed_updates=["message"],
        )
    # Register adapter
    from .dispatcher import ADAPTERS
    adapter = TelegramAdapter(_bot)
    ADAPTERS["telegram"] = adapter
    # Register identity resolver
    # ...

async def shutdown_telegram():
    global _bot
    if _bot:
        await _bot.session.close()
        _bot = None

def get_bot() -> Bot:
    assert _bot is not None, "Telegram bot not initialized"
    return _bot
```

### Key Design Decisions

| Decision | Why |
|----------|-----|
| Singleton Bot instance | python-telegram-bot manages its own httpx session pool internally; creating multiple Bot instances wastes connection pools |
| `async with bot:` in init only | Initializes the session; don't wrap every send_message in `async with` — it would re-init per message |
| No Application class | Its `run_webhook()` takes over the event loop — incompatible with FastAPI lifespan model |
| `set_webhook()` on startup | Ensures webhook URL is current even if it changed between deployments (Coolify) |
| `HTTPXRequest` with timeout | Telegram Bot API can be slow; explicit timeout prevents hanging the FastAPI worker |
| `allowed_updates=["message"]` | Nova only cares about incoming text messages; reduces webhook payload volume |

### Config Changes

```python
# app/config.py — add:
telegram_bot_token: str = ""
telegram_bot_secret_token: str = ""
public_base_url: str = ""  # e.g. "https://nova.example.com"
```

---

## 6. Telegram OTP Integration

### Recommendation: Generalize `whatsapp_verification_codes` → `channel_verification_codes`

The OTP flow for Telegram is identical to WhatsApp except:

| Aspect | WhatsApp | Telegram |
|--------|----------|----------|
| Channel ID | E.164 phone number | Telegram `chat_id` (int64) |
| OTP delivery channel | Same WhatsApp number being verified | The Telegram bot sends it to the user's chat |
| Security model | Someone must physically have the phone | Someone must have the Telegram bot chat |

### Flow

```
1. User opens dashboard → requests Telegram linking
2. Dashboard calls POST /api/preferences/request-telegram-code (new endpoint)
3. Backend: generates code, INSERTs into channel_verification_codes (channel='telegram')
4. Backend: sends code via telegram_adapter.send_message(chat_id, "Your code is XXXXXX")
5. User enters code in dashboard
6. Dashboard calls POST /api/preferences/verify-telegram-code (new endpoint)
7. Backend: validates code, INSERTs into channel_identities (channel='telegram', channel_id=chat_id)
8. Backend: updates user_preferences.channels_enabled to include 'telegram'
```

### Schema for OTP

```sql
-- After rename from whatsapp_verification_codes → channel_verification_codes
-- Existing columns: id, user_id, whatsapp_number, code, attempts, expires_at, created_at
-- New columns: channel (TEXT), channel_id (TEXT)

-- WhatsApp path: channel=whatsapp, channel_id=whatsapp_number (for compat)
-- Telegram path: channel=telegram, channel_id=chat_id
```

### Endpoint Design

Don't create separate endpoints — generalize the existing ones:

```python
# POST /api/preferences/request-code
# Add optional "channel" field to RequestCodeRequest

class RequestCodeRequest(BaseModel):
    user: str
    number: str = ""        # WhatsApp-specific
    channel: str = "whatsapp"  # "whatsapp" | "telegram"
    chat_id: str = ""       # Telegram-specific

# Route dispatches based on channel
```

Actually, **separate endpoints are cleaner** for v1 since the parameters and validation logic differ significantly (phone number format vs chat_id). Keep `/api/preferences/request-code` for WhatsApp, add `/api/preferences/request-telegram-code` for Telegram. Consolidate later if a third channel arrives.

---

## Patterns to Follow

### Pattern 1: Adapter-per-channel with flat modules

**What:** Each channel is a single `.py` file implementing the same two-method interface (`send_message`, `resolve_user`), plus channel-specific webhook parsing.
**When:** Always for channel code. Never put webhook logic in `main.py`.
**Example:**
```python
# Minimal adapter skeleton
class TelegramAdapter:
    def __init__(self, bot: Bot):
        self._bot = bot

    async def send_message(self, channel_id: str, text: str, *, proactive: bool = False) -> None:
        await self._bot.send_message(chat_id=int(channel_id), text=text)

    async def resolve_user(self, channel_id: str) -> str:
        # Query channel_identities
        ...

    async def process_incoming(self, update: dict) -> None:
        msg = update.get("message", {})
        if not msg.get("text"):
            return
        chat_id = str(msg["chat"]["id"])
        user_name = await self.resolve_user(chat_id)
        if user_name == "household":
            await self.send_message(chat_id, "Sorry, you are not authorized.")
            return
        await self._update_last_active(user_name, "telegram")
        reply = await run_agent(msg["text"], user=user_name)
        await self.send_message(chat_id, reply)
```

### Pattern 2: Dispatcher as single outbound fan-out

**What:** All outbound messages go through `dispatcher.send_to_user()` which resolves channel + DND in one place.
**When:** Scheduler, DND queue flush, email alerts, task reminders — everything.
**Why:** Keeps channel logic out of business logic. Scheduler should not know or care about WhatsApp vs Telegram.

### Pattern 3: Identity resolution via channel_identities table

**What:** Single lookup table mapping `(channel, channel_id) → user_id`. Both inbound and outbound resolve through this.
**When:** Every inbound message (resolve sender) and every outbound proactive (resolve target).

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Hardcoding channel in scheduler

**What:** `if channel == "telegram": send_telegram(...) else: send_whatsapp(...)`
**Why bad:** Every new channel requires touching every scheduler function.
**Instead:** `dispatcher.send_to_user(user_name, text)` — dispatcher knows which adapter to use.

### Anti-Pattern 2: python-telegram-bot Application class

**What:** Using `ApplicationBuilder().build().run_webhook()` 
**Why bad:** Takes over the event loop, incompatible with FastAPI. Also overkill for a single-token bot.
**Instead:** Raw `Bot` instance + manual FastAPI webhook endpoint.

### Anti-Pattern 3: One column per channel identity in user_preferences

**What:** Adding `telegram_chat_id`, `signal_uuid`, `discord_user_id` columns to user_preferences.
**Why bad:** Every new channel = schema migration + queries with N COALESCE patterns.
**Instead:** `channel_identities` table with `channel` discriminator column.

### Anti-Pattern 4: Separate webhook router files per channel not sharing prefix

**What:** `/telegram-webhook`, `/whatsapp-hook` — ad-hoc paths.
**Why bad:** Inconsistent paths, harder to configure reverse proxy, documentation confusion.
**Instead:** All under `/webhooks/{channel}`.

---

## Scalability Considerations

| Concern | At 2 users | At 10 users | At 100 users |
|---------|-----------|-------------|--------------|
| Identity resolution | Direct table scan | Same — tiny table | Add index on `(channel, channel_id)` |
| Outbound dispatch | Direct lookup | Same | Add Redis cache for `last_active_channel` if hot |
| Webhook throughput | ~1 msg/min | Same | FastAPI BackgroundTasks sufficient; upgrade to queue if >10 msg/sec |
| Bot session pool | Single Bot instance | Same | Same — httpx connection pool handles concurrent sends |

---

## Suggested Build Order (Dependency Chain)

This is the critical ordering constraint for the roadmap:

```
Phase 1: Schema + Channel Adapter Skeleton
  ├── 1a. Migration: user_preferences columns (last_active_channel, channels_enabled)
  ├── 1b. Migration: CREATE channel_identities + backfill from whatsapp_number
  ├── 1c. Migration: rename whatsapp_verification_codes → channel_verification_codes + add channel column
  ├── 1d. Create channels/ package: __init__.py (ChannelAdapter), dispatcher.py, webhook_router.py
  └── 1e. Refactor whatsapp.py into channels/whatsapp.py (same logic, new home, adapter interface)

Phase 2: Telegram Bot Foundation
  ├── 2a. Config: add telegram_bot_token, telegram_bot_secret_token, public_base_url
  ├── 2b. Create channels/telegram.py: TelegramAdapter + incoming webhook handler
  ├── 2c. Register in config.py + lifespan init/shutdown
  ├── 2d. Wire POST /webhooks/telegram in webhook_router.py
  └── 2e. Test: incoming message → agent → reply (full loop, single user)

Phase 3: Multi-Channel Identity
  ├── 3a. Create channels/identity.py: resolve_user(channel, channel_id) using channel_identities table
  ├── 3b. Update user_from_whatsapp() to use identity.py (or deprecate)
  ├── 3c. Update inbound handlers: both update last_active_channel after each message
  └── 3d. Test: message from each channel correctly resolves user

Phase 4: Outbound Push Dispatcher
  ├── 4a. Create dispatcher.py: send_to_user() with channel resolution
  ├── 4b. Move DND queue logic from whatsapp.py to dispatcher
  ├── 4c. Refactor ALL 5 scheduler call sites to use dispatcher
  ├── 4d. Refactor queued_notifications table to be channel-agnostic (add channel column)
  └── 4e. Test: proactive briefings route to correct channel

Phase 5: Telegram OTP Linking
  ├── 5a. Dashboard: add Telegram linking UI (enter chat_id or /start with bot)
  ├── 5b. Backend: POST /api/preferences/request-telegram-code
  ├── 5c. Backend: POST /api/preferences/verify-telegram-code
  ├── 5d. Write to channel_identities + update channels_enabled
  └── 5e. Test: full OTP flow — dashboard sends code, bot delivers it, user confirms
```

### Dependency Notes

- **Phase 1 must come first** — schema changes are the foundation everything else builds on
- **Phase 1e (refactor WhatsApp) should come before Phase 2** — validates the abstraction works on existing channel first
- **Phase 3 can be parallel with Phase 2** if different developers, but identity resolution must be solid before Phase 4
- **Phase 4 depends on Phase 3** — dispatcher needs identity resolution to find which channel+ID to send to
- **Phase 5 depends on Phase 2** — needs working Telegram bot to deliver OTP messages
- **Phase 5 can be parallel with Phase 4** — OTP is a separate flow from proactive push

---

## Confidence Assessment

| Area | Confidence | Basis |
|------|------------|-------|
| Channel adapter pattern | HIGH | Direct code analysis shows clean 3-point coupling; adapter eliminates duplication |
| Schema design | HIGH | Existing table structure analyzed; column additions are minimal-risk migrations |
| Dispatcher pattern | HIGH | 5 call sites identified; pattern proven in multi-channel systems |
| Telegram Bot lifecycle | HIGH | Verified via python-telegram-bot v22.8 docs; Bot is async context manager |
| OTP generalization | MEDIUM | Flow is straightforward but rename of verification_codes table has migration risk |
| Webhook routing | HIGH | FastAPI APIRouter pattern is standard; secret_token auth verified from Telegram API docs |

## Sources

- Telegram Bot API official documentation: https://core.telegram.org/bots/api (fetched 2026-07-12, API v10.1)
- Telegram webhook setup guide: https://core.telegram.org/bots/webhooks (fetched 2026-07-12)
- python-telegram-bot v22.8 Bot class docs: https://docs.python-telegram-bot.org/en/stable/telegram.bot.html (fetched 2026-07-12)
- Direct codebase analysis of `services/nova-core/app/` (all files, HIGH confidence)
