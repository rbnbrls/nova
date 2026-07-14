<!-- GSD:project-start source:PROJECT.md -->

## Project

**Nova**

Nova is a private, self-hosted household assistant for Ruben & Méral. It runs on their own Proxmox GPU server and is reachable by WhatsApp, voice (ESPHome satellites + iPhone via Home Assistant), and a LAN dashboard. It keeps a shared household plan — tasks, calendar, and important email from a shared Outlook mailbox — behind a single channel-agnostic agent ("Nova Core").

**Core Value:** A private, fully local household assistant that Ruben & Méral can reach by text or voice, keeping a shared plan (tasks, calendar, important email) — reasoning and data never leave the house.

### Constraints

- **Privacy**: All reasoning and household data stay local (Ollama on-box); only WhatsApp (Meta Cloud API) and the shared Outlook mailbox (Microsoft Graph) are permitted to touch the public internet. Never introduce cloud-LLM calls.
- **Hardware**: Single GPU (~16GB VRAM) shared between the chat model and Whisper STT — a real ceiling on model size/quantization choices.
- **Deployment**: Git-push-to-deploy via Coolify only (Phase 1) — no manual production changes outside that path.
- **Existing infra**: Home Assistant is reused as-is for voice I/O; do not replace or fork it.
- **Compliance/reliability**: WhatsApp integration uses the official Meta Cloud API (not an unofficial library), per prior decision.

<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->

## Technology Stack

## Languages

- Python 3.12 - `services/nova-core/` (FastAPI agent service), `services/ops-bridge/` (webhook bridge)
- Bash - `ops/*.sh` closed-loop CI/CD and incident-management scripts
- SQL - `infra/postgres/init/01_schema.sql` schema bootstrap
- YAML - `infra/vector/vector.yaml` (Vector observability pipeline config), `docker-compose.yml`

## Runtime

- Python 3.12-slim (Docker base image, see `services/nova-core/Dockerfile`)
- Deployed as Docker containers orchestrated by Coolify on a single "Nova AI" VM (see `docker-compose.yml` header comment)
- pip, with pinned versions in `requirements.txt` per service
- Lockfile: none (plain `requirements.txt` with `==` pins, not a lockfile format like `poetry.lock`/`uv.lock`)

## Frameworks

- FastAPI 0.115.6 - `services/nova-core/app/main.py`, `services/ops-bridge/app.py` (HTTP API framework for both Python services)
- Uvicorn 0.34.0 (`[standard]` extras) - ASGI server, entrypoint via `CMD ["uvicorn", "app.main:app", ...]` in each Dockerfile
- Pydantic 2.10.4 / pydantic-settings 2.7.1 - request/response schemas (`services/nova-core/app/models.py`) and env-based settings (`services/nova-core/app/config.py`)
- Not detected - no test framework, test files, or test config found in either service
- Docker (multi-service, one Dockerfile per service: `services/nova-core/Dockerfile`, `services/ops-bridge/Dockerfile`)
- Docker Compose - `docker-compose.yml` orchestrates all services for local dev and (via Coolify) production

## Key Dependencies

- httpx 0.28.1 - async HTTP client used for calling Ollama (`services/nova-core/app/llm.py`), Forgejo API (`services/ops-bridge/app.py`)
- pgvector (`pgvector/pgvector:pg16` image) - Postgres extension for vector similarity search, used for the `memories` table embeddings (`infra/postgres/init/01_schema.sql`)
- Ollama (`ollama/ollama:latest`, GPU-accelerated) - self-hosted LLM inference server; model `qwen3:14b` for chat, `nomic-embed-text` for embeddings (`services/nova-core/app/config.py`)
- Wyoming protocol services - `rhasspy/wyoming-whisper` (STT, GPU) and `rhasspy/wyoming-piper` (TTS) for voice I/O, integrated with Home Assistant's Assist pipeline (`docker-compose.yml`)
- Vector (`timberio/vector:latest-alpine`) - log/metrics shipping agent, ships Docker logs + host metrics to OpenObserve (`infra/vector/vector.yaml`)
- Caddy 2 - reverse proxy / TLS termination (`Caddyfile`), routes `/dashboard/*` and default traffic to `nova-core:8080`

## Configuration

- Root `.env` file (referenced via `env_file: .env` in `docker-compose.yml` for `nova-core`, `vector`, `ops-bridge`); `.env.example` documents required vars (not read for security — see forbidden files policy)
- `services/nova-core/app/config.py` uses `pydantic-settings.BaseSettings` with `env_file=".env"` and sensible defaults (e.g. `nova_env`, `ollama_base_url`, `postgres_*`, `nova_whatsapp_users`)
- `services/ops-bridge/app.py` reads config directly via `os.environ.get(...)` (no pydantic-settings): `FORGEJO_URL`, `FORGEJO_REPO`, `FORGEJO_TOKEN`, `BRIDGE_TOKEN`, `BRIDGE_ALERT_LABELS`
- `ops/config.env` (gitignored, copied from `ops/config.env.example`) configures the bash ops loop (Coolify API token, Forgejo, Codex CLI args) - see `ops/lib.sh`
- `ops/secrets/infra.env.example` - template for infra-provisioning secrets (Proxmox audit script)
- `services/nova-core/Dockerfile`, `services/ops-bridge/Dockerfile` - both `python:3.12-slim`, non-buffered/no-bytecode env, `pip install -r requirements.txt`, exposed on container port 8080
- `docker-compose.yml` - defines all 8 services (nova-core, postgres, ollama, whisper, piper, vector, ops-bridge, caddy)
- `Caddyfile` - reverse proxy config; only the WhatsApp webhook path is intended for public exposure (via Cloudflare Tunnel, commented placeholder)

## Platform Requirements

- Docker + Docker Compose (`docker compose up -d` per `docker-compose.yml` header comment)
- NVIDIA Container Toolkit for local GPU passthrough if running `ollama`/`whisper` with GPU acceleration
- Single "Nova AI" VM with NVIDIA GPU, provisioned on Proxmox (see `ops/provision/audit-proxmox.sh`)
- Coolify as the deployment/orchestration platform (Phase 1), driving `docker-compose.yml`-equivalent service definitions
- Cloudflare Tunnel for exposing only the WhatsApp webhook publicly (planned, Phase 4 — commented out in `Caddyfile`)

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

## Overview

## Naming Patterns

- Python modules: lowercase, single word or short compound, no underhistorical prefixes — `agent.py`, `config.py`, `identity.py`, `llm.py`, `models.py`, `main.py` (`services/nova-core/app/`)
- Tool modules grouped under `app/tools/` by domain: `calendar.py`, `email.py`, `tasks.py`, `base.py` (`services/nova-core/app/tools/`)
- Ops scripts: lowercase verb names — `deploy.sh`, `heal.sh`, `issue.sh`, `observe.sh`, `pipeline.sh`, `triage.sh` (`ops/`)
- `snake_case`, verb-first: `run_agent`, `is_ready`, `tool_specs`, `call_tool` (`services/nova-core/app/agent.py`, `app/llm.py`, `app/tools/__init__.py`)
- Private/internal helpers prefixed with underscore: `_resolve_label_ids`, `_fingerprint` (`services/ops-bridge/app.py`)
- `snake_case` throughout; short scoped names in comprehensions (`m`, `n`, `l`)
- Module-level constants are `UPPER_SNAKE_CASE`: `MAX_TOOL_ITERATIONS`, `SYSTEM_PROMPT` (`services/nova-core/app/agent.py`), `FORGEJO_URL`, `BRIDGE_TOKEN`, `ALERT_LABELS` (`services/ops-bridge/app.py`)
- Module-level caches/registries are lowercase with type hint: `TOOLS: dict[str, "Tool"] = {}` (`services/nova-core/app/tools/base.py`), `_label_ids: dict[str, int] = {}` (`services/ops-bridge/app.py`)
- Pydantic models: `PascalCase` nouns, no `Model`/`Schema` suffix — `ChatMessage`, `ChatCompletionRequest`, `Choice`, `ChatCompletionResponse` (`services/nova-core/app/models.py`)
- Plain dataclasses: `PascalCase` — `Tool` (`services/nova-core/app/tools/base.py`)
- Settings class is singular `Settings`, instantiated once as lowercase `settings` (`services/nova-core/app/config.py`)

## Code Style

- No formatter config detected (no `pyproject.toml`, `black`, or `ruff` config). Match existing style manually: 4-space indents, double quotes for strings, trailing commas in multi-line literals.
- Every module opens with a one-to-few-line docstring describing its role, followed by `from __future__ import annotations` (`services/nova-core/app/*.py`, all modules).
- Line length generally kept under ~100 chars; long strings are built with implicit string concatenation across lines (`services/ops-bridge/app.py:82-90`, `services/nova-core/app/agent.py:13-19`).
- No linter config detected. Bash scripts consistently start with `set -euo pipefail` (`ops/lib.sh:4`) — apply this to any new ops script.

## Import Organization

- None used. All intra-service imports are relative (`.module` or `..package`) within `services/nova-core/app/`. `services/ops-bridge/app.py` is a flat single-file service with no local imports.

## Error Handling

- Tool execution never raises to the caller: `Tool.run` wraps `fn(**kwargs)` in `try/except Exception` and returns the error as a string (`error: {exc}`) so the LLM sees the failure instead of the process crashing (`services/nova-core/app/tools/base.py:38-41`).
- FastAPI endpoints validate at the boundary and raise `HTTPException` directly for auth/validation failures, e.g. `raise HTTPException(status_code=401, detail="bad or missing X-Bridge-Token")` (`services/ops-bridge/app.py:69-70`).
- HTTP client calls use `resp.raise_for_status()` immediately after each `httpx` request rather than manual status checks (`services/ops-bridge/app.py:46,99,122`; `services/nova-core/app/llm.py:26`).
- `is_ready()`-style health checks swallow expected transient errors narrowly: `except httpx.HTTPError: return False` — catch the specific exception type, not bare `Exception`, when the failure is expected/normal (`services/nova-core/app/llm.py:33-34`).
- Payload parsing that may fail falls back to a safe default rather than raising, e.g. `except Exception: payload = {"raw": ...}` when JSON body parsing fails (`services/ops-bridge/app.py:72-75`).
- Bash scripts use a shared `die()` helper that logs and exits 1 (`ops/lib.sh:20`), and `require()` to assert a command exists before using it (`ops/lib.sh:22-24`).

## Logging

- Use `%s`-style lazy formatting, not f-strings, in log calls: `log.info("alert %s deduped onto issue #%s", fp, issue["number"])` (`services/ops-bridge/app.py:109`)
- Bash scripts log via a shared `log()` helper that timestamps every line: `printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"` (`ops/lib.sh:19`)

## Comments

- Module docstrings explain the "why" / role of the file, not just what's inside — e.g. `services/nova-core/app/agent.py:1-4` explains the loop is channel-agnostic.
- Inline comments mark stubs and future work explicitly with `# TODO(PhaseN): ...` referencing the roadmap phase that will replace the stub (`services/nova-core/app/tools/tasks.py:31,47,58`; `services/nova-core/app/main.py:48,54`).
- Non-obvious behavior gets a short trailing or preceding comment, e.g. `# Only pass through arguments the function actually declares.` (`services/nova-core/app/tools/base.py:33`).
- Every public async function/endpoint has a one-line docstring stating intent, e.g. `"""Run one turn: returns Nova's final text reply.` (`services/nova-core/app/agent.py:23`). No formal JSDoc/TSDoc-equivalent (Google/NumPy style) is enforced — docstrings are prose, sometimes with a following blank-line elaboration.

## Function Design

## Module Design

<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

## System Overview

```text

```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Nova Core API | FastAPI entrypoint: health, chat completions, dashboard stubs | `services/nova-core/app/main.py` |
| Agent loop | LLM ↔ tools iteration until final text reply | `services/nova-core/app/agent.py` |
| LLM client | Thin async wrapper over Ollama's `/api/chat` | `services/nova-core/app/llm.py` |
| Identity resolver | Maps channel-specific sender IDs to a household `User` | `services/nova-core/app/identity.py` |
| Settings | Env-based configuration (pydantic-settings) | `services/nova-core/app/config.py` |
| API schemas | OpenAI-compatible request/response models | `services/nova-core/app/models.py` |
| Tool registry | Decorator-based registration of LLM-callable tools | `services/nova-core/app/tools/base.py` |
| Household tools | Task/calendar/email tool implementations (stubs) | `services/nova-core/app/tools/{tasks,calendar,email}.py` |
| Ops bridge | Webhook: OpenObserve alert → deduped Forgejo issue | `services/ops-bridge/app.py` |
| DB schema | Users, tasks, memories (pgvector), messages tables | `infra/postgres/init/01_schema.sql` |
| Log shipping | Ships container logs/host metrics to OpenObserve | `infra/vector/vector.yaml` |
| Reverse proxy | LAN dashboard/API + webhook routing | `Caddyfile` |
| Ops scripts | Incident triage/heal/deploy/observe pipeline | `ops/*.sh` |

## Pattern Overview

- One FastAPI service (`nova-core`) owns all reasoning, tools, and memory — channels never talk to the LLM or DB directly.
- Tool-calling is registry-based: adding a new capability means writing an `@tool`-decorated async function; the agent loop and OpenAI-shaped tool specs are automatically wired up.
- Local-only inference: Ollama runs the model in-cluster via Docker Compose with GPU passthrough; no cloud LLM calls.
- Separate "ops" subsystem (ops-bridge + shell scripts) implements a fully independent closed-loop incident-response pipeline (monitoring → issue → automated Codex fix), decoupled from the household-assistant domain logic.
- Everything is stub-first: Phase 3 (this snapshot) has real HTTP/agent plumbing but tool bodies return `[stub]` strings; DB schema exists but is not yet wired into tool implementations.

## Layers

- Purpose: Translate a channel-specific message (WhatsApp webhook payload, Home Assistant Assist request, raw HTTP) into the OpenAI-compatible `/v1/chat/completions` shape.
- Location: `services/nova-core/app/main.py` (only the generic API endpoint currently exists; WhatsApp webhook is a documented future addition under `/webhooks/*`).
- Depends on: `identity.py` to resolve `user`.
- Purpose: FastAPI routes; owns the OpenAI-compatible contract.
- Location: `services/nova-core/app/main.py`, `services/nova-core/app/models.py`.
- Depends on: `agent.py`, `llm.py` (health check).
- Purpose: Runs the LLM↔tool iteration (max 6 rounds) for a single conversational turn.
- Location: `services/nova-core/app/agent.py`.
- Contains: system prompt construction, message history assembly, tool-call dispatch loop.
- Depends on: `llm.py`, `tools` package.
- Used by: `main.py`'s `/v1/chat/completions` handler.
- Purpose: Household capabilities exposed to the LLM as callable functions (tasks, calendar, email).
- Location: `services/nova-core/app/tools/` (`base.py` registry + decorator, `tasks.py`, `calendar.py`, `email.py`).
- Depends on: nothing yet (stubs); will depend on Postgres (tasks), CalDAV (calendar), MS Graph (email) once Phase 5 lands.
- Used by: `agent.py` via `tools.tool_specs()` / `tools.call_tool()`.
- Purpose: Isolates all Ollama HTTP interaction behind `chat()` / `is_ready()`.
- Location: `services/nova-core/app/llm.py`.
- Used by: `agent.py`, `main.py` (health check).
- Purpose: Persistent state — household users, tasks, long-term vector memories, short-term conversation history.
- Location: `infra/postgres/init/01_schema.sql` (schema), `postgres` service in `docker-compose.yml`.
- Not yet used: tool stubs do not query it; `database_url` is built in `config.py` but no ORM/driver code exists yet.
- Purpose: Closed-loop incident management independent of the household-assistant runtime.
- Location: `services/ops-bridge/app.py` (webhook + Forgejo issue creation), `ops/*.sh` (triage/heal/deploy/observe pipeline), `infra/vector/vector.yaml` (log/metric shipping).

## Data Flow

### Primary Request Path (chat turn)

### Incident Response Path (ops)

- Conversation short-term memory is passed explicitly per-request as `history` (list of prior messages) from the caller — no server-side session store is wired up yet, though a `messages` table exists in the schema for this purpose.
- Long-term memory is modeled as embedding-searchable rows in the `memories` table (`infra/postgres/init/01_schema.sql`) but not yet read/written by any code path.

## Key Abstractions

- Purpose: Represents one LLM-callable household capability with a JSON-Schema parameter spec.
- Examples: `add_task`, `list_tasks`, `complete_task` in `app/tools/tasks.py`; equivalents in `calendar.py`, `email.py`.
- Pattern: `@tool(name, description, parameters)` decorator registers the function into a module-level `TOOLS` dict; `Tool.run()` filters incoming LLM arguments down to the function's actual signature and injects `user` if declared.
- Purpose: Frozen dataclass representing a household member (`Ruben`, `Meral`, or `household`) — the identity unit threaded through the agent loop and tool calls.
- Pattern: Channel-specific resolvers (currently only `user_from_whatsapp`) map external identifiers to a `User`, falling back to the shared `HOUSEHOLD` sentinel.
- Purpose: Single source of runtime config, loaded from `.env` via `pydantic_settings.BaseSettings`.
- Pattern: Module-level singleton `settings = Settings()`, imported wherever config is needed (`llm.py`, `identity.py`, `main.py`).

## Entry Points

- Location: `services/nova-core/app/main.py`
- Triggers: HTTP requests (uvicorn, run via `Dockerfile`/`docker-compose.yml` `nova-core` service, port 8080).
- Responsibilities: health check, OpenAI-compatible chat endpoint, dashboard read endpoints (stubbed).
- Location: `services/ops-bridge/app.py`
- Triggers: OpenObserve webhook POST to `/webhooks/openobserve` (port 8085 externally, 8080 internally).
- Responsibilities: alert fingerprinting/dedup, Forgejo issue creation/comment.
- Location: `ops/pipeline.sh`, `ops/deploy.sh`, `ops/observe.sh`, `ops/triage.sh`, `ops/heal.sh`, `ops/issue.sh`
- Triggers: git push (Coolify deploy), cron/manual invocation for triage/heal.
- Responsibilities: deploy verification, issue triage, autonomous fix generation via headless Codex.

## Architectural Constraints

- **Threading:** Fully async — FastAPI + `httpx.AsyncClient` throughout; no explicit worker threads. Single-process per container (uvicorn default).
- **Global state:** Module-level singletons: `settings` (`config.py`), `TOOLS` registry (`tools/base.py`), `_WHATSAPP_USERS` mapping (`identity.py`), `_label_ids` cache (`ops-bridge/app.py`). All process-local, not shared across replicas — fine for single-instance deployment but would need externalizing if scaled horizontally.
- **No persistence layer wired yet:** `database_url` is computed in `config.py` but no DB driver/session code exists in `nova-core/app`; tool stubs are pure in-memory string returns. Adding real persistence (Phase 5) requires introducing a DB client (e.g., `asyncpg`/`sqlalchemy`) not currently a dependency.
- **Privacy boundary:** All LLM inference is local (Ollama); only WhatsApp (Meta Cloud API) and Outlook (MS Graph) are permitted to touch the public internet, per `README.md`. Do not introduce cloud-LLM calls in `llm.py` or elsewhere.

## Anti-Patterns

### None identified as active anti-patterns

## Error Handling

- `Tool.run()` wraps `fn(**kwargs)` in try/except and returns `f"error: {exc}"` on failure, keeping the agent loop alive (`services/nova-core/app/tools/base.py:38-41`).
- `llm.is_ready()` swallows `httpx.HTTPError` and returns `False` for health-check purposes (`services/nova-core/app/llm.py:39`).
- `ops-bridge` raises `HTTPException(401)` for bad/missing bridge tokens and uses `resp.raise_for_status()` to propagate Forgejo API failures as 5xx (`services/ops-bridge/app.py:69,46,99,121`).
- No centralized error middleware or structured error responses defined yet in `main.py`.

## Cross-Cutting Concerns

<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.Codex/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-Codex-profile` -- do not edit manually.
<!-- GSD:profile-end -->
