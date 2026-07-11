<!-- refreshed: 2026-07-11 -->
# Architecture

**Analysis Date:** 2026-07-11

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                     Channels (entry points)                  │
├──────────────────┬──────────────────┬───────────────────────┤
│  WhatsApp webhook │  Voice (HA Assist│  Direct API / iPhone  │
│  (Phase 4, TODO)  │  via Wyoming)    │  `/v1/chat/completions`│
└────────┬─────────┴────────┬─────────┴──────────┬────────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│               Nova Core — FastAPI app (single brain)         │
│  `services/nova-core/app/main.py`                             │
│  identity.py → agent.py (agent loop) → tools/*                │
└────────┬─────────────────────────┬────────────────────────────┘
         │                         │
         ▼                         ▼
┌─────────────────────┐   ┌─────────────────────────────────────┐
│  Ollama (local LLM)  │   │  Household data tools (stubs)        │
│  `app/llm.py`         │   │  `app/tools/{tasks,calendar,email}.py`│
└──────────────────────┘   └───────────────┬─────────────────────┘
                                            ▼
                              ┌─────────────────────────────┐
                              │ Postgres/pgvector (tasks,     │
                              │ memories, messages)            │
                              │ `infra/postgres/init/01_schema.sql` │
                              └─────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│         Ops closed loop (separate concern, own service)      │
│  OpenObserve alert → `services/ops-bridge/app.py` → Forgejo   │
│  issue → `ops/triage.sh` → `ops/heal.sh` (Claude Code headless)│
└─────────────────────────────────────────────────────────────┘
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

**Overall:** Single channel-agnostic backend service ("brain") exposing an OpenAI-compatible API, fronted by multiple thin channel adapters (WhatsApp, voice, direct API). Classic agent-loop pattern (LLM decides to call tools, tool results fed back into context) rather than a fixed pipeline.

**Key Characteristics:**
- One FastAPI service (`nova-core`) owns all reasoning, tools, and memory — channels never talk to the LLM or DB directly.
- Tool-calling is registry-based: adding a new capability means writing an `@tool`-decorated async function; the agent loop and OpenAI-shaped tool specs are automatically wired up.
- Local-only inference: Ollama runs the model in-cluster via Docker Compose with GPU passthrough; no cloud LLM calls.
- Separate "ops" subsystem (ops-bridge + shell scripts) implements a fully independent closed-loop incident-response pipeline (monitoring → issue → automated Claude Code fix), decoupled from the household-assistant domain logic.
- Everything is stub-first: Phase 3 (this snapshot) has real HTTP/agent plumbing but tool bodies return `[stub]` strings; DB schema exists but is not yet wired into tool implementations.

## Layers

**Channel adapters (partial/pending):**
- Purpose: Translate a channel-specific message (WhatsApp webhook payload, Home Assistant Assist request, raw HTTP) into the OpenAI-compatible `/v1/chat/completions` shape.
- Location: `services/nova-core/app/main.py` (only the generic API endpoint currently exists; WhatsApp webhook is a documented future addition under `/webhooks/*`).
- Depends on: `identity.py` to resolve `user`.

**API / request layer:**
- Purpose: FastAPI routes; owns the OpenAI-compatible contract.
- Location: `services/nova-core/app/main.py`, `services/nova-core/app/models.py`.
- Depends on: `agent.py`, `llm.py` (health check).

**Agent loop (core domain logic):**
- Purpose: Runs the LLM↔tool iteration (max 6 rounds) for a single conversational turn.
- Location: `services/nova-core/app/agent.py`.
- Contains: system prompt construction, message history assembly, tool-call dispatch loop.
- Depends on: `llm.py`, `tools` package.
- Used by: `main.py`'s `/v1/chat/completions` handler.

**Tool layer:**
- Purpose: Household capabilities exposed to the LLM as callable functions (tasks, calendar, email).
- Location: `services/nova-core/app/tools/` (`base.py` registry + decorator, `tasks.py`, `calendar.py`, `email.py`).
- Depends on: nothing yet (stubs); will depend on Postgres (tasks), CalDAV (calendar), MS Graph (email) once Phase 5 lands.
- Used by: `agent.py` via `tools.tool_specs()` / `tools.call_tool()`.

**LLM client layer:**
- Purpose: Isolates all Ollama HTTP interaction behind `chat()` / `is_ready()`.
- Location: `services/nova-core/app/llm.py`.
- Used by: `agent.py`, `main.py` (health check).

**Data layer:**
- Purpose: Persistent state — household users, tasks, long-term vector memories, short-term conversation history.
- Location: `infra/postgres/init/01_schema.sql` (schema), `postgres` service in `docker-compose.yml`.
- Not yet used: tool stubs do not query it; `database_url` is built in `config.py` but no ORM/driver code exists yet.

**Ops/observability layer (separate from the assistant domain):**
- Purpose: Closed-loop incident management independent of the household-assistant runtime.
- Location: `services/ops-bridge/app.py` (webhook + Forgejo issue creation), `ops/*.sh` (triage/heal/deploy/observe pipeline), `infra/vector/vector.yaml` (log/metric shipping).

## Data Flow

### Primary Request Path (chat turn)

1. Client (WhatsApp/voice/API) POSTs to `/v1/chat/completions` (`services/nova-core/app/main.py:28`).
2. Handler resolves `user` and prior `history`, calls `run_agent()` (`services/nova-core/app/main.py:35`).
3. `run_agent` builds the system+history+user message list and calls `llm.chat()` with the registered tool specs (`services/nova-core/app/agent.py:35`).
4. If the model returns `tool_calls`, each is dispatched via `tools.call_tool()`, results appended as `role: tool` messages, and the loop repeats (up to `MAX_TOOL_ITERATIONS = 6`) (`services/nova-core/app/agent.py:42-49`).
5. Once the model replies without tool calls, the text is returned and wrapped into an OpenAI-shaped `ChatCompletionResponse` (`services/nova-core/app/main.py:37`).

### Incident Response Path (ops)

1. Vector ships container logs/host metrics to OpenObserve (`infra/vector/vector.yaml`).
2. OpenObserve fires an alert to `ops-bridge`'s `/webhooks/openobserve` (`services/ops-bridge/app.py:64`), authenticated via `X-Bridge-Token`.
3. Bridge fingerprints the alert (name+stream hash) and either comments on an existing open Forgejo issue or creates a new one labeled `incident`/`monitoring`/`auto-heal` (`services/ops-bridge/app.py:79-125`).
4. `ops/triage.sh` polls Forgejo for `auto-heal`-labeled issues and invokes `ops/heal.sh`, which runs Claude Code headless to diagnose and commit a fix, then reports back as an issue comment.
5. `ops/deploy.sh` / `ops/observe.sh` handle git-push-driven deploys (via Coolify) and post-deploy verification.

**State Management:**
- Conversation short-term memory is passed explicitly per-request as `history` (list of prior messages) from the caller — no server-side session store is wired up yet, though a `messages` table exists in the schema for this purpose.
- Long-term memory is modeled as embedding-searchable rows in the `memories` table (`infra/postgres/init/01_schema.sql`) but not yet read/written by any code path.

## Key Abstractions

**Tool (`services/nova-core/app/tools/base.py`):**
- Purpose: Represents one LLM-callable household capability with a JSON-Schema parameter spec.
- Examples: `add_task`, `list_tasks`, `complete_task` in `app/tools/tasks.py`; equivalents in `calendar.py`, `email.py`.
- Pattern: `@tool(name, description, parameters)` decorator registers the function into a module-level `TOOLS` dict; `Tool.run()` filters incoming LLM arguments down to the function's actual signature and injects `user` if declared.

**User (`services/nova-core/app/identity.py`):**
- Purpose: Frozen dataclass representing a household member (`Ruben`, `Meral`, or `household`) — the identity unit threaded through the agent loop and tool calls.
- Pattern: Channel-specific resolvers (currently only `user_from_whatsapp`) map external identifiers to a `User`, falling back to the shared `HOUSEHOLD` sentinel.

**Settings (`services/nova-core/app/config.py`):**
- Purpose: Single source of runtime config, loaded from `.env` via `pydantic_settings.BaseSettings`.
- Pattern: Module-level singleton `settings = Settings()`, imported wherever config is needed (`llm.py`, `identity.py`, `main.py`).

## Entry Points

**Nova Core FastAPI app:**
- Location: `services/nova-core/app/main.py`
- Triggers: HTTP requests (uvicorn, run via `Dockerfile`/`docker-compose.yml` `nova-core` service, port 8080).
- Responsibilities: health check, OpenAI-compatible chat endpoint, dashboard read endpoints (stubbed).

**ops-bridge FastAPI app:**
- Location: `services/ops-bridge/app.py`
- Triggers: OpenObserve webhook POST to `/webhooks/openobserve` (port 8085 externally, 8080 internally).
- Responsibilities: alert fingerprinting/dedup, Forgejo issue creation/comment.

**Ops shell pipeline:**
- Location: `ops/pipeline.sh`, `ops/deploy.sh`, `ops/observe.sh`, `ops/triage.sh`, `ops/heal.sh`, `ops/issue.sh`
- Triggers: git push (Coolify deploy), cron/manual invocation for triage/heal.
- Responsibilities: deploy verification, issue triage, autonomous fix generation via headless Claude Code.

## Architectural Constraints

- **Threading:** Fully async — FastAPI + `httpx.AsyncClient` throughout; no explicit worker threads. Single-process per container (uvicorn default).
- **Global state:** Module-level singletons: `settings` (`config.py`), `TOOLS` registry (`tools/base.py`), `_WHATSAPP_USERS` mapping (`identity.py`), `_label_ids` cache (`ops-bridge/app.py`). All process-local, not shared across replicas — fine for single-instance deployment but would need externalizing if scaled horizontally.
- **No persistence layer wired yet:** `database_url` is computed in `config.py` but no DB driver/session code exists in `nova-core/app`; tool stubs are pure in-memory string returns. Adding real persistence (Phase 5) requires introducing a DB client (e.g., `asyncpg`/`sqlalchemy`) not currently a dependency.
- **Privacy boundary:** All LLM inference is local (Ollama); only WhatsApp (Meta Cloud API) and Outlook (MS Graph) are permitted to touch the public internet, per `README.md`. Do not introduce cloud-LLM calls in `llm.py` or elsewhere.

## Anti-Patterns

### None identified as active anti-patterns

The codebase is small and early-stage (Phase 3, scaffolded). No entrenched anti-patterns were found; the main risk area is the growing gap between the tool signatures/specs (stable, Phase 3) and their stub bodies (`[stub]` strings), which must be replaced carefully to keep the JSON-Schema `parameters` and function signatures in sync (see `services/nova-core/app/tools/tasks.py`).

## Error Handling

**Strategy:** Fail-soft within the agent loop; tool exceptions are caught and surfaced as text to the model rather than raising.

**Patterns:**
- `Tool.run()` wraps `fn(**kwargs)` in try/except and returns `f"error: {exc}"` on failure, keeping the agent loop alive (`services/nova-core/app/tools/base.py:38-41`).
- `llm.is_ready()` swallows `httpx.HTTPError` and returns `False` for health-check purposes (`services/nova-core/app/llm.py:39`).
- `ops-bridge` raises `HTTPException(401)` for bad/missing bridge tokens and uses `resp.raise_for_status()` to propagate Forgejo API failures as 5xx (`services/ops-bridge/app.py:69,46,99,121`).
- No centralized error middleware or structured error responses defined yet in `main.py`.

## Cross-Cutting Concerns

**Logging:** Standard library `logging`, configured per-service (`ops-bridge/app.py` sets `logging.basicConfig(level=logging.INFO)`); `nova-core` has a `nova_log_level` setting but no logging configuration wired up yet in `main.py`. Container logs are shipped centrally via Vector → OpenObserve (`infra/vector/vector.yaml`).

**Validation:** Pydantic models (`app/models.py`) validate the chat API request/response shapes; tool JSON-Schema `parameters` validate/describe arguments to the LLM (enforced by the model, not by server-side JSON-Schema validation in `Tool.run()`).

**Authentication:** No auth on `nova-core`'s API yet (LAN-only, behind Caddy). `ops-bridge` requires a shared-secret `X-Bridge-Token` header (`services/ops-bridge/app.py:69`). Forgejo API calls use a token (`FORGEJO_TOKEN` env var).

---

*Architecture analysis: 2026-07-11*
