# Coding Conventions

**Analysis Date:** 2026-07-11

## Overview

Nova is a small Python (FastAPI) monorepo with two services (`services/nova-core`, `services/ops-bridge`) plus a bash-based ops toolkit (`ops/*.sh`). No linter, formatter, or type-checker config is present (no `.flake8`, `ruff.toml`, `pyproject.toml`, `.pre-commit-config.yaml`, or `shellcheck` config found). Conventions below are inferred purely from observed code style — there is no enforcement tooling, so new code must match these patterns by hand.

## Naming Patterns

**Files:**
- Python modules: lowercase, single word or short compound, no underhistorical prefixes — `agent.py`, `config.py`, `identity.py`, `llm.py`, `models.py`, `main.py` (`services/nova-core/app/`)
- Tool modules grouped under `app/tools/` by domain: `calendar.py`, `email.py`, `tasks.py`, `base.py` (`services/nova-core/app/tools/`)
- Ops scripts: lowercase verb names — `deploy.sh`, `heal.sh`, `issue.sh`, `observe.sh`, `pipeline.sh`, `triage.sh` (`ops/`)

**Functions:**
- `snake_case`, verb-first: `run_agent`, `is_ready`, `tool_specs`, `call_tool` (`services/nova-core/app/agent.py`, `app/llm.py`, `app/tools/__init__.py`)
- Private/internal helpers prefixed with underscore: `_resolve_label_ids`, `_fingerprint` (`services/ops-bridge/app.py`)

**Variables:**
- `snake_case` throughout; short scoped names in comprehensions (`m`, `n`, `l`)
- Module-level constants are `UPPER_SNAKE_CASE`: `MAX_TOOL_ITERATIONS`, `SYSTEM_PROMPT` (`services/nova-core/app/agent.py`), `FORGEJO_URL`, `BRIDGE_TOKEN`, `ALERT_LABELS` (`services/ops-bridge/app.py`)
- Module-level caches/registries are lowercase with type hint: `TOOLS: dict[str, "Tool"] = {}` (`services/nova-core/app/tools/base.py`), `_label_ids: dict[str, int] = {}` (`services/ops-bridge/app.py`)

**Types:**
- Pydantic models: `PascalCase` nouns, no `Model`/`Schema` suffix — `ChatMessage`, `ChatCompletionRequest`, `Choice`, `ChatCompletionResponse` (`services/nova-core/app/models.py`)
- Plain dataclasses: `PascalCase` — `Tool` (`services/nova-core/app/tools/base.py`)
- Settings class is singular `Settings`, instantiated once as lowercase `settings` (`services/nova-core/app/config.py`)

## Code Style

**Formatting:**
- No formatter config detected (no `pyproject.toml`, `black`, or `ruff` config). Match existing style manually: 4-space indents, double quotes for strings, trailing commas in multi-line literals.
- Every module opens with a one-to-few-line docstring describing its role, followed by `from __future__ import annotations` (`services/nova-core/app/*.py`, all modules).
- Line length generally kept under ~100 chars; long strings are built with implicit string concatenation across lines (`services/ops-bridge/app.py:82-90`, `services/nova-core/app/agent.py:13-19`).

**Linting:**
- No linter config detected. Bash scripts consistently start with `set -euo pipefail` (`ops/lib.sh:4`) — apply this to any new ops script.

## Import Organization

**Order (Python):**
1. `from __future__ import annotations` (always first, every module)
2. Standard library imports (`hashlib`, `json`, `logging`, `os`, `datetime`, `time`, `uuid`, `inspect`, `dataclasses`, `typing`)
3. Third-party imports (`httpx`, `fastapi`, `pydantic`, `pydantic_settings`)
4. Local/relative imports last, using relative syntax: `from . import llm, tools`, `from .config import settings`, `from .models import ...` (`services/nova-core/app/main.py:13-18`)

**Path Aliases:**
- None used. All intra-service imports are relative (`.module` or `..package`) within `services/nova-core/app/`. `services/ops-bridge/app.py` is a flat single-file service with no local imports.

## Error Handling

**Patterns:**
- Tool execution never raises to the caller: `Tool.run` wraps `fn(**kwargs)` in `try/except Exception` and returns the error as a string (`error: {exc}`) so the LLM sees the failure instead of the process crashing (`services/nova-core/app/tools/base.py:38-41`).
- FastAPI endpoints validate at the boundary and raise `HTTPException` directly for auth/validation failures, e.g. `raise HTTPException(status_code=401, detail="bad or missing X-Bridge-Token")` (`services/ops-bridge/app.py:69-70`).
- HTTP client calls use `resp.raise_for_status()` immediately after each `httpx` request rather than manual status checks (`services/ops-bridge/app.py:46,99,122`; `services/nova-core/app/llm.py:26`).
- `is_ready()`-style health checks swallow expected transient errors narrowly: `except httpx.HTTPError: return False` — catch the specific exception type, not bare `Exception`, when the failure is expected/normal (`services/nova-core/app/llm.py:33-34`).
- Payload parsing that may fail falls back to a safe default rather than raising, e.g. `except Exception: payload = {"raw": ...}` when JSON body parsing fails (`services/ops-bridge/app.py:72-75`).
- Bash scripts use a shared `die()` helper that logs and exits 1 (`ops/lib.sh:20`), and `require()` to assert a command exists before using it (`ops/lib.sh:22-24`).

## Logging

**Framework:** Python `logging` module, module-level logger named after the service: `log = logging.getLogger("ops-bridge")` with `logging.basicConfig(level=logging.INFO)` at import time (`services/ops-bridge/app.py:20-21`). `services/nova-core` does not yet configure a logger (log level is exposed via `Settings.nova_log_level` but unused — see CONCERNS).

**Patterns:**
- Use `%s`-style lazy formatting, not f-strings, in log calls: `log.info("alert %s deduped onto issue #%s", fp, issue["number"])` (`services/ops-bridge/app.py:109`)
- Bash scripts log via a shared `log()` helper that timestamps every line: `printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"` (`ops/lib.sh:19`)

## Comments

**When to Comment:**
- Module docstrings explain the "why" / role of the file, not just what's inside — e.g. `services/nova-core/app/agent.py:1-4` explains the loop is channel-agnostic.
- Inline comments mark stubs and future work explicitly with `# TODO(PhaseN): ...` referencing the roadmap phase that will replace the stub (`services/nova-core/app/tools/tasks.py:31,47,58`; `services/nova-core/app/main.py:48,54`).
- Non-obvious behavior gets a short trailing or preceding comment, e.g. `# Only pass through arguments the function actually declares.` (`services/nova-core/app/tools/base.py:33`).

**Docstrings:**
- Every public async function/endpoint has a one-line docstring stating intent, e.g. `"""Run one turn: returns Nova's final text reply.` (`services/nova-core/app/agent.py:23`). No formal JSDoc/TSDoc-equivalent (Google/NumPy style) is enforced — docstrings are prose, sometimes with a following blank-line elaboration.

## Function Design

**Size:** Small and single-purpose; endpoint handlers stay under ~15 lines and delegate to helper functions (`_resolve_label_ids`, `_fingerprint` in `services/ops-bridge/app.py`).

**Parameters:** Keyword-only parameters used for anything beyond the primary positional argument, enforced with `*`, e.g. `async def run_agent(user_message: str, *, user: str, history: list[dict] | None = None)` (`services/nova-core/app/agent.py:22`). Tool functions accept `user` as a keyword param that the framework injects only if declared (`services/nova-core/app/tools/base.py:36-37`).

**Return Values:** Async functions that talk to an LLM/tool return plain strings (chat content) or `dict` (raw API bodies); FastAPI handlers return Pydantic response models or plain `dict` for simple/stub endpoints (`services/nova-core/app/main.py:24-25,47,53`).

## Module Design

**Exports:** No `__all__` lists; modules expose whatever is public by naming convention (no leading underscore). Tool modules self-register into a shared `TOOLS` dict via the `@tool(...)` decorator import side-effect rather than explicit exports (`services/nova-core/app/tools/base.py:44-51`, consumed via `from . import llm, tools` in `app/agent.py:9`).

**Barrel Files:** `services/nova-core/app/tools/__init__.py` acts as a barrel — it imports all tool submodules (for registration side effects) and re-exports `tool_specs()`/`call_tool()` helpers used by `agent.py`. Read this file when adding a new tool module to ensure it's imported here.

---

*Convention analysis: 2026-07-11*
