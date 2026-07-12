# Phase 17 Context: Reliability Hardening

## Source
ROADMAP.md Phase 17 goal + success criteria.

## Existing Implementation (already shipped)
- **Friendly fallback:** `main.py` catches all exceptions from `run_agent` and returns "Nova is having trouble right now, please try again later." (200, not 500)
- **History truncation:** `agent.py` `_truncate_history()` keeps last 20 messages, safely avoiding tool-response splits
- **Iteration budget:** `agent.py` loops max `settings.nova_max_iterations` (default 6)
- **Timeout:** `agent.py` wraps the turn in `asyncio.timeout(60)`

## What This Phase Adds

### Retry/Backoff for Transient Ollama Errors
- Add exponential backoff to `llm.chat()` for transient failures (connection refused, 5xx from Ollama)
- Backoff: 1s → 2s → 4s, max 3 retries
- Only retry transient errors; permanent errors (400, auth) fail immediately
- Log each retry attempt

### Wall-Clock Budget
- Current 60s asyncio timeout is per-iteration, not per-turn
- Add an overall per-turn budget of 120s (covers all iterations + retries)
- Return friendly fallback if budget exceeded

### Test Coverage
- Add tests for retry/backoff behavior (mock Ollama to fail transiently)
- Add tests for overall timeout
- Add tests for long-conversation truncation boundary

## Deferred Ideas
None.
