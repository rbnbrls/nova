# Domain Pitfalls

**Domain:** Adding Telegram as second messaging channel to existing WhatsApp-backed Nova household assistant
**Researched:** 2026-07-12
**Overall confidence:** HIGH

---

## Critical Pitfalls

Mistakes that cause rewrites, security holes, or break the existing working WhatsApp channel.

### Pitfall 1: Applying HMAC Raw-Body Verification to Telegram Webhooks

**What goes wrong:** The existing WhatsApp webhook handler in `security.py` computes HMAC-SHA256 over the raw HTTP body using `X-Hub-Signature-256`. Someone writing the Telegram webhook handler copy-pastes this pattern and tries to verify the request body with a shared secret — but Telegram does NOT send a body signature at all. The code will silently reject every legitimate Telegram webhook or, worse, be bypassed by an attacker who doesn't understand the difference.

**Why it happens:** Telegram's webhook authentication is fundamentally different from Meta's. Meta sends `X-Hub-Signature-256: sha256=<hmac_hex>` computed over the raw POST body using the app secret. Telegram sends `X-Telegram-Bot-Api-Secret-Token: <secret_token>` — a static bearer-token-style header with NO body signing. The token is set during `setWebhook(secret_token=...)` and Telegram repeats it verbatim in every webhook POST.

**Consequences:**
- If you replicate the HMAC pattern: all Telegram webhooks return 401, bot appears dead
- If you use naive `==` string comparison instead of `hmac.compare_digest()`: timing attack vulnerability
- If you forget to check the header at all: any POST to `/webhooks/telegram` is accepted, allowing spoofed messages attributed to authorized users

**Prevention:**
```python
# CORRECT Telegram webhook verification — header match, not body signature
def verify_telegram_secret_token(header_value: str | None, expected: str) -> bool:
    if not header_value or not expected:
        return False
    return hmac.compare_digest(header_value, expected)
```
- Set `secret_token` when calling `setWebhook()` (1-256 chars, alphanumeric plus `-` and `_`)
- Verify via `hmac.compare_digest()` for constant-time comparison
- The existing `verify_whatsapp_signature(body, signature, secret)` function in `security.py` must NOT be reused — add a separate `verify_telegram_secret_token()` function

**Detection:** All Telegram webhook requests return 401; or security audit shows non-constant-time string comparison on a secret header.

---

### Pitfall 2: Non-Atomic Last-Active-Channel Updates Creating Race Conditions

**What goes wrong:** Both webhook handlers (WhatsApp and Telegram) write to the same `users.last_inbound_at` column. If a user sends a message on WhatsApp and Telegram within milliseconds, the two concurrent UPDATE statements race. The "last active" channel becomes whichever UPDATE wins — potentially the wrong one for outbound push routing.

**Why it happens:** The current code does `UPDATE users SET last_inbound_at = now() WHERE name = $1` as a bare UPDATE without any channel tracking. Adding Telegram creates two independent writers to the same row. Postgres will serialize these at the row level, but the logical ordering is lost — there's no way to know which channel was truly "last active."

**Consequences:**
- Morning briefings, task reminders, and email alerts route to the wrong channel
- User expects notification on the app they're actively using, but gets it on the other one
- Very hard to reproduce in testing — only manifests under concurrent usage

**Prevention:**
- Add a `last_active_channel TEXT` column (values: `'whatsapp'`, `'telegram'`, `NULL`)
- Use a single atomic UPDATE that sets both `last_inbound_at` and `last_active_channel` in one statement:
  ```sql
  UPDATE users SET last_inbound_at = now(), last_active_channel = 'telegram'
  WHERE name = $1
  ```
- In the push router: if `last_active_channel IS NULL`, fall back to the user's preferred/default channel (WhatsApp, since that's the existing path)
- Accept that simultaneous messages within the same second will be arbitrary — this is acceptable for a 2-person household

**Detection:** Push notifications arriving on the wrong channel; logs showing `last_inbound_at` updated but channel not tracked.

---

### Pitfall 3: Telegram Webhook Retries Causing Duplicate Agent Executions

**What goes wrong:** Telegram retries webhook delivery if it receives a non-2xx response or timeout. The existing WhatsApp handler uses `BackgroundTasks.add_task()` to process messages asynchronously and immediately returns 200. If the Telegram webhook handler does the same but the agent loop fails or takes too long, Telegram retries — and the bot processes the SAME message twice, sending duplicate replies.

**Why it happens:** The official Telegram docs explicitly state: "In case of an unsuccessful request (a request with response HTTP status code different from 2XY), we will repeat the request and give up after a reasonable amount of attempts." The `update_id` field in each Update object is designed for exactly this scenario — deduplication — but only if you track it.

**Consequences:**
- User sees double replies ("Here is your calendar... Here is your calendar...")
- Agent tool calls execute twice (task created twice, email checked twice)
- Conversation history is polluted with duplicate assistant messages
- `last_inbound_at` and `last_active_channel` are updated twice (harmless but wasteful)

**Prevention:**
- Create a `processed_updates` table or use the existing pattern:
  ```sql
  CREATE TABLE IF NOT EXISTS processed_telegram_updates (
      update_id BIGINT PRIMARY KEY,
      processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
  );
  ```
- Before processing, check `INSERT ... ON CONFLICT (update_id) DO NOTHING` — if the row already exists, discard the update
- Return HTTP 200 immediately (within 1-2 seconds) to prevent Telegram from retrying; use background tasks for the agent loop (same pattern as WhatsApp)
- Store `update_id` from the Update object — it's a sequential integer, unique per bot

**Detection:** Duplicate agent replies in Telegram chat; duplicate rows in `messages` table with identical content and timestamps.

---

### Pitfall 4: Cold-Start State — Users Without Telegram Get Push Failures

**What goes wrong:** After adding Telegram support, the push router (scheduler.py) queries `user_preferences` to determine where to send notifications. If a new column `telegram_chat_id` is NULL for existing users (who only have WhatsApp), the push router may attempt to send to Telegram first (alphabetical order, wrong conditional logic) and silently fail — or worse, skip the user entirely.

**Why it happens:** The current code in `scheduler.py` has every send function hardcoded to WhatsApp:
```python
from .whatsapp import send_whatsapp_message
# Every function calls send_whatsapp_message(number, text, proactive=True)
```
This must be refactored to a channel-agnostic push gateway. During the refactoring:
- Users who haven't linked Telegram have `telegram_chat_id = NULL`
- Users who haven't linked WhatsApp have `whatsapp_number = NULL` (unlikely but possible)
- The `queued_notifications` table currently hardcodes `whatsapp_number TEXT NOT NULL`

**Consequences:**
- Morning briefings stop working for all users during the refactoring window
- Email alerts silently dropped if the new code tries Telegram first and the user hasn't linked it
- The `process_queued_notifications` DND queue fails to flush because it queries by `whatsapp_number`

**Prevention:**
- Introduce a `send_push(user_name, text, proactive)` function that checks channel preferences:
  1. Look up user's `last_active_channel` (or default to `whatsapp` if NULL)
  2. If channel is `telegram` and `telegram_chat_id IS NOT NULL` → send via Telegram
  3. Else if channel is `whatsapp` and `whatsapp_number IS NOT NULL` → send via WhatsApp
  4. Else: try the other channel as fallback
  5. Else: queue for later delivery
- **Additive-only migration**: new columns added with `ADD COLUMN IF NOT EXISTS`, existing data untouched
- The `queued_notifications` table needs a `channel` column and nullable `telegram_chat_id`
- Run the existing pytest suite after refactoring — `test_scheduler.py` should catch regressions

**Detection:** Morning briefings not received; `queued_notifications` growing without being flushed; no errors in logs because failures are silent.

---

### Pitfall 5: Telegram Message Size Limit (4096 Chars) Breaking Briefings

**What goes wrong:** The existing `send_morning_briefing_for_user()` and `send_weekly_briefing_for_user()` in `scheduler.py` build a single text string containing tasks, calendar events, and emails. WhatsApp has a ~65,536 character limit for messages. Telegram caps at **4096 characters** per `sendMessage` call. A busy week with 10 tasks, 5 events, and 3 emails easily exceeds 4096 chars — the Telegram API call fails with `Bad Request: message is too long`.

**Why it happens:** Telegram's `sendMessage` hard limit is 1-4096 characters after entity parsing. This is well-documented but easy to miss because WhatsApp's limit is ~16x higher. The existing briefing formatting uses `*bold*` markdown which is Telegram-compatible, but the LENGTH is the problem.

**Consequences:**
- Morning/weekly briefings fail silently for Telegram users
- Error logs show `Bad Request: message is too long` but no user-visible feedback
- WhatsApp-only users are unaffected, creating an asymmetric failure

**Prevention:**
- Add a message-chunking utility that splits long text at paragraph boundaries, respecting the 4096 limit:
  ```python
  TELEGRAM_MAX_TEXT = 4096
  WHATSAPP_MAX_TEXT = 65536  # effectively unlimited for our use
  
  async def send_with_chunking(send_fn, text, chat_id, max_chars):
      if len(text) <= max_chars:
          return await send_fn(chat_id, text)
      chunks = split_at_paragraphs(text, max_chars)
      results = []
      for i, chunk in enumerate(chunks):
          if i > 0:
              await asyncio.sleep(1)  # Respect 1 msg/sec per chat limit
          results.append(await send_fn(chat_id, chunk))
      return results
  ```
- Apply the limit PER CHANNEL in the send function, not at the briefing builder
- Test with artificially long briefings in the eval suite

**Detection:** Telegram briefings not received; `Bad Request: message is too long` in error logs.

---

## Moderate Pitfalls

Mistakes that cause bugs or degraded experience but not total failure.

### Pitfall 6: Telegram `chat_id` is a 64-Bit Integer — Postgres Column Type Trap

**What goes wrong:** Telegram's `chat.id` is defined as "This number may have more than 32 significant bits." It requires a 64-bit integer or double-precision float. If the `telegram_chat_id` column in Postgres is defined as `INTEGER` (32-bit), large chat IDs overflow silently or cause insertion errors.

**Why it happens:** The official Telegram docs explicitly warn: "This number may have more than 32 significant bits and some programming languages may have difficulty/silent defects in interpreting it. But it has at most 52 significant bits, so a signed 64-bit integer or double-precision float type are safe."

**Prevention:**
- Use `BIGINT` for the `telegram_chat_id` column in Postgres:
  ```sql
  ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS telegram_chat_id BIGINT;
  ```
- In Python/asyncpg, the value fits in a standard Python `int` (arbitrary precision), so no application-level concern
- Verify by requesting the chat ID from a real Telegram user and checking it fits in 32 bits (it often does for private chats, but supergroups can exceed `2^31 - 1`)

---

### Pitfall 7: FastAPI `request.body()` vs `request.json()` Breaking Verification

**What goes wrong:** The existing WhatsApp handler reads raw bytes via `body = await request.body()` and then manually `json.loads(body)`. This pattern is CORRECT for WhatsApp signature verification because you need the exact bytes Meta signed. Someone writing the Telegram handler might use `await request.json()` which parses the body into a dict — this is fine for Telegram (no body signing needed) but creates inconsistency in the codebase and makes it harder to reason about what each handler is receiving.

**Why it happens:** Inconsistency between handlers: one reads raw bytes, the other reads parsed JSON. The real danger is if someone later "cleans up" the WhatsApp handler to use `request.json()` — this would break the HMAC signature check because the bytes consumed by FastAPI for JSON parsing may differ from the raw wire bytes (whitespace normalization, encoding differences).

**Prevention:**
- Document the pattern: WhatsApp MUST use `request.body()` (raw bytes for HMAC); Telegram CAN use `request.json()` (no body signing)
- Add a comment in the WhatsApp handler: `# IMPORTANT: must use request.body() for HMAC, never request.json()`
- Both handlers should exist side-by-side without refactoring the WhatsApp path

---

### Pitfall 8: Telegram Bot Can't See Messages from Other Bots — Testing Trap

**What goes wrong:** During testing, someone sends messages via a test bot or automation script, expecting the Nova bot to see and respond. Telegram bots **cannot** see messages from other bots, regardless of privacy mode settings. The bot appears to silently ignore all test messages.

**Why it happens:** The official FAQ states: "Bots talking to each other could potentially get stuck in unwelcome loops. To avoid this, we decided that bots will not be able to see messages from other bots regardless of mode."

**Prevention:**
- All manual testing must be done from a real Telegram user account (Ruben or Méral's personal accounts)
- Automated integration tests must POST webhook payloads directly to the FastAPI endpoint (same as existing WhatsApp tests in `test_webhooks.py`)
- Document this limitation in the Telegram adapter module docstring

---

### Pitfall 9: Telegram Privacy Mode Affecting Group Message Visibility

**What goes wrong:** If the Telegram bot is added to a household group chat, it may not receive all messages. Bots with privacy mode enabled (the DEFAULT) only receive: commands, replies to the bot, messages sent via the bot, and service messages. The bot silently ignores normal household conversation.

**Why it happens:** Telegram's default privacy mode restricts bot message visibility in groups. For Nova's use case (1:1 private chats), this isn't an issue. But if someone wants to add Nova to a family group chat, they'll hit this.

**Prevention:**
- For v3.0: explicitly document that Telegram support is **private chat only** (1:1 DMs)
- Disable privacy mode via @BotFather (`/setprivacy` → Disable) if group support is planned later
- The identity resolution must only handle messages from `chat.type == "private"` initially
- Add a validation check: if `chat.type != "private"`, log and ignore (don't process group messages)

---

### Pitfall 10: Migration of `queued_notifications` Table for Multi-Channel

**What goes wrong:** The existing `queued_notifications` table has `whatsapp_number TEXT NOT NULL`. When adding Telegram, this table needs to support Telegram delivery too. But changing `whatsapp_number` from `NOT NULL` to nullable is a breaking change for the existing `process_queued_notifications()` function.

**Why it happens:** The DND queue currently only supports WhatsApp. The column `whatsapp_number` is used both as the destination AND as part of the identity. Adding Telegram requires either a new `channel` column with nullable per-channel destination fields, or a redesign.

**Prevention:**
- **Additive approach**: add `channel TEXT DEFAULT 'whatsapp'` and `telegram_chat_id BIGINT` columns to `queued_notifications`
- Make `whatsapp_number` nullable: `ALTER TABLE queued_notifications ALTER COLUMN whatsapp_number DROP NOT NULL`
- Update `process_queued_notifications()` to route based on the `channel` column
- This change is safe because existing rows have `whatsapp_number` populated and get `channel = 'whatsapp'` as default

---

## Minor Pitfalls

### Pitfall 11: Telegram Formatting Differences — Markdown Variants

**What goes wrong:** The existing briefing text uses WhatsApp-style `*bold*` markdown. Telegram uses `MarkdownV2` or `HTML` parse modes with different escaping rules. Characters like `_`, `*`, `[`, `]`, `(`, `)`, `~`, `` ` ``, `>`, `#`, `+`, `-`, `=`, `|`, `{`, `}`, `.`, `!` are reserved in MarkdownV2 and must be escaped. Unescaped characters cause `Bad Request: can't parse entities` errors.

**Prevention:**
- Use `parse_mode="HTML"` for Telegram instead of Markdown — HTML is simpler to escape (only `<`, `>`, `&` need escaping)
- Convert existing briefing format: `*bold*` → `<b>bold</b>`
- Or add a format-conversion layer in the push gateway that adapts text per channel

---

### Pitfall 12: Telegram File Download Limit (20 MB) vs WhatsApp Media

**What goes wrong:** If Nova later supports file/photo intake via Telegram, the `getFile` API only works for files up to 20 MB. The WhatsApp integration doesn't have file intake yet, so this is a forward-looking concern.

**Prevention:**
- For v3.0: ignore non-text message types (photos, documents) from Telegram, reply with "I can only handle text messages for now"
- If file support is added later, check `file_size` before calling `getFile()`
- The 50 MB upload limit (sendDocument) is fine for outbound files

---

### Pitfall 13: Telegram `update_id` Sequence Reset After Inactivity

**What goes wrong:** The official docs warn: "If there are no new updates for at least a week, then identifier of the next update will be chosen randomly instead of sequentially." If the deduplication table assumes monotonically increasing `update_id` values and uses offset-based cleanup, the reset could cause issues.

**Prevention:**
- Store `update_id` as a PRIMARY KEY (not as an offset index) — the dedup table is just a set, not a sequence
- Periodically purge entries older than 24 hours: `DELETE FROM processed_telegram_updates WHERE processed_at < now() - interval '24 hours'`
- Don't assume `update_id` is sequential or monotonically increasing

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Telegram webhook handler | #1 HMAC vs secret token, #3 duplicate updates | Write a separate `verify_telegram_secret_token()` in `security.py`; add `processed_telegram_updates` dedup table before the handler processes |
| DB schema migration for Telegram prefs | #4 cold-start push failures, #6 BIGINT trap, #10 queued_notifications | Add columns additive-only with `IF NOT EXISTS`; make push router fall back to WhatsApp when Telegram is NULL |
| Push gateway refactoring | #4 routing defaults, #5 message size, #11 formatting | Build `send_push()` with explicit channel resolution order; add chunking utility; convert briefing format per-channel |
| Last-active-channel tracking | #2 race conditions | Single atomic UPDATE setting both `last_inbound_at` and `last_active_channel` |
| Telegram OTP linking flow | #8 bot-to-bot testing trap | Test from real Telegram accounts; use webhook POST simulation for automated tests |
| Scheduler migration (briefings to multi-channel) | #5 4096 char limit, #4 cold-start | Chunk long messages; test with artificially long briefings; ensure fallback chain |
| Regression testing existing WhatsApp | #7 body vs json, existing tests breaking | Run full pytest suite after every change; WhatsApp handler must NOT be refactored to use `request.json()` |

---

## Rollback Safety

The highest-risk change is the push gateway refactor. If it breaks, ALL outbound notifications stop.

**Safe rollback strategy:**
1. The push gateway should be an abstraction layer over the existing `send_whatsapp_message()` — not a replacement
2. A feature flag (`NOVA_TELEGRAM_ENABLED=false` by default) gates the Telegram path
3. If the new `send_push()` function fails, it falls back to the existing `send_whatsapp_message()` directly
4. The existing WhatsApp webhook handler (`/webhooks/whatsapp`) must remain completely unchanged — it already works
5. Database migrations are additive (`ADD COLUMN IF NOT EXISTS`) — they don't break if the code is rolled back (the new columns are simply unused)
6. Test the WhatsApp-only path explicitly: set `NOVA_TELEGRAM_ENABLED=false`, run full test suite, verify all existing WhatsApp tests pass

**Cannot-rollback changes (must be correct the first time):**
- Making `whatsapp_number` nullable in `queued_notifications` — existing code assumes it's NOT NULL
- Adding new columns with `NOT NULL` and no default — would break INSERT statements

---

## Sources

- **Telegram Bot API — setWebhook `secret_token`**: Official API docs at `core.telegram.org/bots/api#setwebhook` (HIGH confidence — official primary source, verified 2026-07-12)
- **Telegram Bot FAQ — rate limits**: `core.telegram.org/bots/faq#broadcasting-to-users` (HIGH confidence — official FAQ)
- **Telegram Webhook Guide — SSL, ports, security**: `core.telegram.org/bots/webhooks` (HIGH confidence — official guide)
- **Telegram Bot API — sendMessage limits (4096 chars)**: `core.telegram.org/bots/api#sendmessage` (HIGH confidence — official API reference)
- **Telegram Bot API — editMessageText (48-hour limit)**: `core.telegram.org/bots/api#editmessagetext` (HIGH confidence — official API reference)
- **Telegram Bot API — deleteMessage (48-hour limit)**: `core.telegram.org/bots/api#deletemessage` (HIGH confidence — official API reference)
- **Telegram Bot API — chat.id size warning**: `core.telegram.org/bots/api#chat` (HIGH confidence — official docs explicitly warn about 32-bit limitations)
- **Existing Nova codebase**: `services/nova-core/app/security.py`, `whatsapp.py`, `main.py`, `identity.py`, `scheduler.py`, `db.py`, `infra/postgres/init/01_schema.sql` (HIGH confidence — codebase analysis)
- **Multi-channel race condition / idempotency patterns**: Engineering reasoning from codebase analysis combined with Telegram's `update_id` semantics (MEDIUM confidence — derived pattern, not from a single authoritative source)
