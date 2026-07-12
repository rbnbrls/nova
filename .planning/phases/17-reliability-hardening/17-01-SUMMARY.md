---
phase: 17-reliability-hardening
plan: 01
subsystem: nova-core
tags:
  - retry
  - logging
  - timeout
  - reliability
  - observability
requires: []
provides: [relog-01, reconf-01, retest-01]
affects:
  - services/nova-core/app/llm.py
  - services/nova-core/app/config.py
  - services/nova-core/app/agent.py
  - services/nova-core/tests/test_reliability.py
tech-stack:
  added:
    - logging (stdlib)
  patterns:
    - Retry logging via log.warning() with attempt/delay attribution
    - Configurable timeout via pydantic-settings with 120s default
    - async test with patched log.warning and settings mutation
key-files:
  created: []
  modified:
    - services/nova-core/app/llm.py
    - services/nova-core/app/config.py
    - services/nova-core/app/agent.py
    - services/nova-core/tests/test_reliability.py
decisions:
  - "Each retry attempt logs a warning with attempt number, max retries, exception, and delay — both for HTTPStatusError (5xx) and RequestError branches."
  - "Per-turn wall-clock timeout default raised from 60s to 120s to accommodate up to 3 retries (1+2+4=7s extra per call × up to 6 iterations)."
  - "Retry logging tests verify log.warning call arguments positionally (format-string args) rather than string-matching the formatted output."
metrics:
  duration_minutes: 4
  tasks: 3
  tests_added: 2
  total_tests_passing: 14
status: complete
completed_date: 2026-07-12
---

# Phase 17 Plan 01: Retry Logging + Configurable Timeout Summary

Add retry-attempt logging to `llm.chat()` and make the per-turn wall-clock timeout configurable via settings (default 120s), with tests that verify both behaviors.

## Tasks

### Task 1: Add retry logging to llm.chat()
- **Status:** Complete
- **Files:** `services/nova-core/app/llm.py`
- **Commit:** `205cb46`
- Added `import logging` and `log = logging.getLogger(__name__)`.
- Added `log.warning()` calls before each `await asyncio.sleep()` in both the `HTTPStatusError` (5xx) and `RequestError` branches.
- Message format: `"Ollama chat attempt %d/%d failed: %s — retrying in %ds"` with attempt number, max_retries, exception, and delay.
- Existing retry/backoff algorithm, `_REQUEST_TIMEOUT`, and request logic unchanged.

### Task 2: Configurable per-turn wall-clock timeout
- **Status:** Complete
- **Files:** `services/nova-core/app/config.py`, `services/nova-core/app/agent.py`
- **Commit:** `2c6b10c`
- Added `nova_max_turn_timeout: int = 120` with descriptive comment to `Settings` class.
- Replaced hardcoded `asyncio.timeout(60)` with `asyncio.timeout(settings.nova_max_turn_timeout)` in `agent.py`.
- All existing tests continue to pass.

### Task 3: Tests for retry logging and configurable timeout
- **Status:** Complete
- **Files:** `services/nova-core/tests/test_reliability.py`
- **Commit:** `c604998`
- **`test_llm_chat_logs_retry_warning`** — mocks `httpx.AsyncClient` returning 500 twice then 200; verifies `log.warning` called 2 times with correct attempt number and delay positional arguments.
- **`test_agent_uses_configurable_timeout`** — patches `settings.nova_max_turn_timeout` to 0.001s and `llm.chat` to sleep 10s; verifies agent returns the friendly timeout fallback.

## Verification Results

```
# All 10 reliability tests pass
cd services/nova-core && .venv/bin/python -m pytest tests/test_reliability.py -x -v
  → 10 passed

# All 4 agent tests pass (backward compatible)
cd services/nova-core && .venv/bin/python -m pytest tests/test_agent.py -x -q
  → 4 passed

# Config defaults to 120
from app.config import settings; print(settings.nova_max_turn_timeout)
  → 120

# Two retry logging branches
grep -c 'log.warning.*retrying' app/llm.py
  → 2
```

## Deviations from Plan

No deviations — plan executed exactly as written.

### Auto-Fixed Issues

**1. [Rule 1 - Bug] `UnboundLocalError: cannot access local variable 'exc'` in RequestError branch**
- **Found during:** Task 1, initial test run
- **Issue:** The `RequestError` handler did not capture the exception (`except httpx.RequestError:` without `as exc`), but the new log.warning line referenced `exc`.
- **Fix:** Changed to `except httpx.RequestError as exc:`.
- **Files modified:** `services/nova-core/app/llm.py`
- **Commit:** Part of `205cb46`

## Known Stubs

None found.

## Threat Flags

None found — all security-relevant surface is within the existing trust boundaries documented in the threat model (T-17-01 through T-17-03).

## Plan Context

- **Plan:** 17-01
- **Wave:** 1
- **Phase:** 17 — Reliability Hardening
- **Requirements:** RELI-01, RELI-02, RELI-03, RELI-04

## All Commits

| Task | Hash | Message |
|------|------|---------|
| 1 | `205cb46` | feat(17-reliability-hardening): add retry logging to llm.chat() |
| 2 | `2c6b10c` | feat(17-reliability-hardening): configurable per-turn wall-clock timeout |
| 3 | `c604998` | test(17-reliability-hardening): add tests for retry logging and configurable timeout |

## Self-Check: PASSED

All created/modified files verified:
- [x] `services/nova-core/app/llm.py` — exists, imports logging, has logger, two log.warning calls
- [x] `services/nova-core/app/config.py` — exists, has nova_max_turn_timeout = 120
- [x] `services/nova-core/app/agent.py` — exists, reads settings.nova_max_turn_timeout
- [x] `services/nova-core/tests/test_reliability.py` — exists, has two new tests
- [x] Commit `205cb46` exists in git log
- [x] Commit `2c6b10c` exists in git log
- [x] Commit `c604998` exists in git log
- [x] All 14 tests pass
