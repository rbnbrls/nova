# Testing Patterns

**Analysis Date:** 2026-07-11

## Test Framework

**Runner:**
- None present. No `pytest`, `unittest`, or JS test runner is configured anywhere in the repo.
- No test dependency in `services/nova-core/requirements.txt` or `services/ops-bridge/requirements.txt` (both list only runtime deps: `fastapi`, `uvicorn`, `httpx`, `pydantic`, `pydantic-settings`).
- No `pytest.ini`, `pyproject.toml`, `tox.ini`, `jest.config.*`, or `vitest.config.*` found anywhere in the repo.

**Assertion Library:**
- Not applicable — no test framework installed.

**Run Commands:**
```bash
# No test command exists yet. Nothing is registered in package.json/Makefile/CI.
```

## Test File Organization

**Location:**
- Not applicable. `find . -iname "*test*"` (excluding `.git`/`.planning`) returns zero results across the entire repository.

**Naming:**
- No convention established yet.

**Structure:**
```
(no test directories exist)
```

## Test Structure

**Suite Organization:**
No test suites exist. When introducing tests, this codebase's style (docstring-first modules, `from __future__ import annotations`, relative imports within `services/nova-core/app/`) suggests placing tests under a new `services/nova-core/tests/` directory using `pytest` + FastAPI's `TestClient`/`httpx.AsyncClient` (already a dependency, so async test clients are cheap to add), mirroring the `app/` package layout (e.g. `tests/test_agent.py`, `tests/tools/test_tasks.py`).

**Patterns:**
- Not established.

## Mocking

**Framework:** None installed (no `unittest.mock` usage found, no `pytest-mock`, `responses`, or `httpx` `MockTransport` usage found in source).

**What would need mocking if tests are added:**
- `app.llm.chat()` (`services/nova-core/app/llm.py:9-26`) — calls out to Ollama over HTTP; must be mocked/stubbed for agent-loop tests.
- `httpx.AsyncClient` calls to the Forgejo API in `services/ops-bridge/app.py` (`_resolve_label_ids`, `openobserve_alert`) — these are the natural mock boundary for ops-bridge tests.
- Tool functions in `services/nova-core/app/tools/*.py` currently return hardcoded `[stub]` strings (no real DB), so early tests would only exercise the JSON-schema/dispatch plumbing in `app/tools/base.py`, not real persistence.

## Fixtures and Factories

**Test Data:**
- None exist. `services/nova-core/app/tools/tasks.py`, `calendar.py`, and `email.py` are themselves stubs returning canned strings (see `# TODO(Phase 5): ...` comments), so there is no real data layer yet to build fixtures against.

**Location:**
- Not applicable.

## Coverage

**Requirements:** None enforced — no coverage tooling (`coverage.py`, `pytest-cov`, `nyc`, `c8`) configured anywhere.

**View Coverage:**
```bash
# Not applicable — no coverage tooling installed.
```

## Test Types

**Unit Tests:** None. Candidates once introduced: `Tool.run` argument-filtering logic (`services/nova-core/app/tools/base.py:32-41`), `_fingerprint`/`_resolve_label_ids` in ops-bridge (`services/ops-bridge/app.py:41-56`).

**Integration Tests:** None. Candidates: `POST /v1/chat/completions` end-to-end with a mocked Ollama backend (`services/nova-core/app/main.py:28-40`); `POST /webhooks/openobserve` end-to-end with a mocked Forgejo API (`services/ops-bridge/app.py:64-125`).

**E2E Tests:** Not used. The closed-loop ops pipeline (`ops/pipeline.sh`, `ops/observe.sh`, `ops/heal.sh`) is the closest thing to end-to-end verification today, but it is an operational/runtime script, not an automated test — it deploys, observes OpenObserve, and self-heals against a live environment rather than asserting behavior in CI.

## Common Patterns

**Async Testing:**
```python
# Not established. Given the codebase is 100% `async def` FastAPI handlers and
# httpx-based clients, `pytest-asyncio` (or pytest's built-in asyncio mode) plus
# `httpx.AsyncClient(transport=ASGITransport(app=app))` would be the natural fit —
# no async test infra exists to reference yet.
```

**Error Testing:**
```python
# Not established. `Tool.run` already normalizes exceptions into `"error: {exc}"`
# strings (services/nova-core/app/tools/base.py:38-41), so error-path tests would
# assert on that string contract rather than on raised exceptions.
```

---

*Testing analysis: 2026-07-11*
