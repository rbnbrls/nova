---
phase: 20-telegram-bot-foundation
plan: 01
subsystem: telegram
tags: [channel-adapter, webhook-router, feature-flag, refactor]
requires: [19-01]
affects: [config, main, telegram, webhook-router, tests, env-example]
tech-stack:
  added: []
  patterns:
    - "ChannelAdapter.register_webhooks registers FastAPI routes via decorator"
    - "register_all_webhooks at module load orchestrates all channel route registration"
    - "Module-level imports for types used in route handler signatures (avoids PEP 563 string-annotation resolution issues)"
key-files:
  created:
    - services/nova-core/app/channels/webhook_router.py — register_all_webhooks function
  modified:
    - services/nova-core/app/config.py — renamed telegram_enabled → nova_telegram_enabled
    - services/nova-core/app/main.py — removed inline telegram route, added register_all_webhooks call
    - services/nova-core/app/channels/telegram.py — moved _handle_telegram_command, implemented register_webhooks
    - services/nova-core/tests/test_telegram.py — updated patch targets and import paths
    - .env.example — added Telegram environment variables section
decisions:
  - "Import Request, BackgroundTasks, HTTPException at telegram.py module level so FastAPI can resolve type annotations even with from __future__ import annotations (PEP 563 string-ification)"
  - "Use module-level get_pool (already imported) in register_webhooks handler instead of re-importing, keeping patch target app.channels.telegram.get_pool consistent"
metrics:
  duration: 310s
  completed_date: 2026-07-12T15:32:05Z
status: complete
---

# Phase 20 Plan 01: Telegram Bot Foundation Summary

Renamed the feature flag from `telegram_enabled` to `nova_telegram_enabled` per user decision D-04, added Telegram env vars to `.env.example`, moved `_handle_telegram_command` from `main.py` into `telegram.py`, implemented `TelegramAdapter.register_webhooks(app)` and `webhook_router.py` with full route registration via the channel adapter pattern.

## Changes by Task

### Task 1: Rename feature flag + Telegram env vars (dc69116)

- **config.py**: Renamed `telegram_enabled: bool = False` → `nova_telegram_enabled: bool = False`. Pydantic Settings auto-derives the env var name `NOVA_TELEGRAM_ENABLED`.
- **main.py**: Updated both references (lifespan line 101 + webhook handler line 489) to use the new flag name.
- **test_telegram.py**: Updated all 6 patch targets from `app.config.settings.telegram_enabled` to `app.config.settings.nova_telegram_enabled`.
- **.env.example**: Added Telegram section after WhatsApp section with `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `NOVA_TELEGRAM_ENABLED`, `NOVA_TELEGRAM_USERS`.

### Task 2: Webhook router, register_webhooks, command move (d197693)

- **telegram.py**: Moved `_handle_telegram_command` from main.py (lines 801-825) as a module-level function with `# Moved from main.py in Phase 20` comment. Implemented `TelegramAdapter.register_webhooks(app)` which registers `POST /webhooks/telegram` via the channel adapter interface.
- **webhook_router.py**: Replaced skeleton with `register_all_webhooks(app)` that iterates over TelegramAdapter and WhatsAppAdapter (WhatsApp remains a no-op for backward compatibility).
- **main.py**: Removed inline `@app.post("/webhooks/telegram")` route, added import of `register_all_webhooks` and call after `app = FastAPI(...)` with running-loop guard.
- **test_telegram.py**: Updated `_handle_telegram_command` import paths (4 occurrences) from `app.main` to `app.channels.telegram`. Fixed `test_duplicate_update_id_returns_accepted` mock target from `app.main.db_get_pool` to `app.channels.telegram.get_pool`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 — Missing correctness] Missing `nova_telegram_enabled` patches in test_telegram.py**
- **Found during:** Task 1 verification
- **Issue:** Tests `test_missing_secret_token_returns_401` and `test_invalid_secret_token_returns_401` did not patch `nova_telegram_enabled=True`, so they returned 404 instead of 401 (channel disabled by default). This was a pre-existing bug in the tests.
- **Fix:** Added `patch("app.config.settings.nova_telegram_enabled", True)` context manager to both tests.
- **Files modified:** `services/nova-core/tests/test_telegram.py`

**2. [Rule 2 — Missing correctness] Invalid mock setup in test_valid_secret_token_returns_accepted**
- **Found during:** Task 1 verification
- **Issue:** The `patch("app.main.db_get_pool")` pattern used `mock_pool.return_value.acquire...` which created a coroutine instead of a proper mock pool, causing `TypeError: 'coroutine' object does not support the asynchronous context manager protocol`.
- **Fix:** Changed to `patch("app.main.db_get_pool", return_value=mock_pool)` with pre-built mock_pool, matching the pattern used in `test_duplicate_update_id_returns_accepted`.
- **Files modified:** `services/nova-core/tests/test_telegram.py`

**3. [Rule 1 — Bug] 422 error from FastAPI due to unresolvable type annotations**
- **Found during:** Task 2 verification (the new handler was returning 422 instead of 401)
- **Issue:** `from __future__ import annotations` at the top of `telegram.py` string-ifies all annotations. FastAPI could not resolve the string `'Request'` and `'BackgroundTasks'` because they were imported inside the `register_webhooks` closure, not at module level. This caused FastAPI to treat them as query parameters.
- **Fix:** Moved `from fastapi import Request, BackgroundTasks, HTTPException` to the module level in `telegram.py` (outside TYPE_CHECKING). Also moved `from ..security import verify_telegram_signature` to module level for consistency.
- **Files modified:** `services/nova-core/app/channels/telegram.py`

**4. [Rule 1 — Bug] Incorrect db_get_pool mock target in test_duplicate_update_id_returns_accepted**
- **Found during:** Task 2 verification
- **Issue:** After moving the route handler from `main.py` to `telegram.py`'s `register_webhooks`, the handler uses `get_pool` from `app.channels.telegram` (module-level import), not `app.main.db_get_pool`. The test's patch of `app.main.db_get_pool` no longer intercepts the handler's database calls.
- **Fix:** Changed patch target from `app.main.db_get_pool` to `app.channels.telegram.get_pool`. Removed unused `from app.main import db_get_pool` statement.
- **Files modified:** `services/nova-core/tests/test_telegram.py`

## Threat Flags

None — no new security surface introduced. All mitigations from the threat model are inherited:

| Threat ID | Mitigation | Status |
|-----------|-----------|--------|
| T-20-01 | `verify_telegram_signature` with `hmac.compare_digest` (constant-time) | Preserved (moved to module-level import) |
| T-20-02 | `INSERT ON CONFLICT DO NOTHING` dedup | Preserved in new handler |
| T-20-03 | `nova_telegram_enabled` defaults to False | Preserved (404 when disabled) |
| T-20-04 | Routes registered at module load time (sync context) | Preserved via `asyncio.run()` guard |

## Known Stubs

None. `_handle_telegram_command` was moved without behavioral changes. All webhooks are now properly registered through the adapter pattern.

## Verdict

- `pytest services/nova-core/tests/test_telegram.py -x`: **24 passed**
- `pytest services/nova-core/tests/test_webhooks.py -x`: **21 passed** (no WhatsApp regression)
- Combined: **45 passed**
- Task 1 grep-based validation: all checks pass
- Task 2 import path audit: all checks pass
