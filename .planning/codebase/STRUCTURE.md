# Codebase Structure

**Analysis Date:** 2026-07-11

## Directory Layout

```
nova/
├── .claude/                  # Claude Code project settings (local permissions)
├── .planning/                # GSD planning artifacts (this document lives here)
├── docs/
│   └── roadmap.md            # Approved build-phase plan (source of truth for phases)
├── infra/
│   ├── postgres/init/        # SQL run on first Postgres container boot
│   │   └── 01_schema.sql     # users, tasks, memories (pgvector), messages tables
│   └── vector/
│       └── vector.yaml       # Vector log/metric shipping config → OpenObserve
├── ops/                       # Closed-loop incident management (independent of app code)
│   ├── incidents/             # (empty, .gitkeep) local incident scratch dir
│   ├── provision/
│   │   └── audit-proxmox.sh   # read-only host/infra audit script
│   ├── secrets/                # (empty, .gitkeep) local secrets dir, gitignored contents
│   │   └── infra.env.example
│   ├── config.env.example
│   ├── deploy.sh               # git-push-driven deploy verification (Coolify)
│   ├── heal.sh                  # runs Claude Code headless to fix auto-heal issues
│   ├── issue.sh                  # Forgejo issue helper (incl. label setup)
│   ├── lib.sh                     # shared shell helpers for the ops scripts
│   ├── observe.sh                  # post-deploy observability checks
│   ├── pipeline.sh                  # orchestrates deploy → observe → triage
│   ├── triage.sh                     # polls auto-heal-labeled Forgejo issues
│   └── README.md
├── services/
│   ├── nova-core/              # The FastAPI "brain" — all channels funnel here
│   │   ├── app/
│   │   │   ├── __init__.py
│   │   │   ├── main.py          # FastAPI routes: /health, /v1/chat/completions, /dashboard/*
│   │   │   ├── agent.py         # LLM ↔ tools agent loop (run_agent)
│   │   │   ├── llm.py           # Ollama chat client
│   │   │   ├── identity.py      # channel identity → household user
│   │   │   ├── config.py        # env-based Settings (pydantic-settings)
│   │   │   ├── models.py        # OpenAI-compatible request/response schemas
│   │   │   └── tools/
│   │   │       ├── __init__.py  # exposes tool_specs()/call_tool() over the registry
│   │   │       ├── base.py      # @tool decorator + Tool dataclass + TOOLS registry
│   │   │       ├── tasks.py     # add_task/list_tasks/complete_task (stubs)
│   │   │       ├── calendar.py  # calendar tools (stubs)
│   │   │       └── email.py     # email tools (stubs)
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── ops-bridge/              # OpenObserve alert → Forgejo issue webhook service
│       ├── app.py                # single-file FastAPI app
│       ├── Dockerfile
│       └── requirements.txt
├── .env.example                 # config template; real secrets live in Coolify
├── Caddyfile                    # reverse proxy: LAN dashboard/API + webhook routing
├── docker-compose.yml            # full local stack: nova-core, postgres, ollama, whisper, piper, vector, ops-bridge, caddy
└── README.md
```

## Directory Purposes

**`services/nova-core/app/`:**
- Purpose: All household-assistant domain logic — the single channel-agnostic "brain."
- Contains: FastAPI routes, agent loop, LLM client, identity resolution, settings, API schemas, tool implementations.
- Key files: `main.py` (routes), `agent.py` (core loop), `tools/base.py` (tool registry pattern).

**`services/nova-core/app/tools/`:**
- Purpose: Household capabilities exposed to the LLM as callable functions.
- Contains: one module per domain (`tasks.py`, `calendar.py`, `email.py`), each using `@tool(...)` from `base.py`.
- Currently all stubs; Phase 5 replaces bodies with real Postgres/CalDAV/MS Graph calls behind the same signatures.

**`services/ops-bridge/`:**
- Purpose: Standalone microservice bridging OpenObserve alerts into Forgejo issues (dedup by fingerprint).
- Contains: single `app.py` FastAPI app, its own `Dockerfile`/`requirements.txt` (deployed as a separate container from `nova-core`).

**`infra/postgres/init/`:**
- Purpose: Database bootstrap — schema is applied once via Postgres's `docker-entrypoint-initdb.d` mechanism.
- Contains: `01_schema.sql` defining `users`, `tasks`, `memories` (pgvector, 768-dim for `nomic-embed-text`), `messages`.
- Note: schema is not idempotent-on-change — edits after first boot require manual migration (no migration tool present).

**`infra/vector/`:**
- Purpose: Log/metric shipping configuration for the `vector` container (ships to OpenObserve).
- Contains: `vector.yaml` only.

**`ops/`:**
- Purpose: Closed-loop incident management — deploy verification, alert triage, automated healing via headless Claude Code. Fully independent of the household-assistant runtime; operates on the git repo and Forgejo issue tracker.
- Contains: bash scripts (`deploy.sh`, `observe.sh`, `triage.sh`, `heal.sh`, `issue.sh`, `pipeline.sh`, `lib.sh`), plus `provision/` (host audit) and `secrets/`/`incidents/` scratch dirs (gitignored contents, `.gitkeep`-tracked dirs).

**`docs/`:**
- Purpose: Long-form project documentation.
- Contains: `roadmap.md`, the approved multi-phase build plan referenced by `README.md`.

## Key File Locations

**Entry Points:**
- `services/nova-core/app/main.py`: FastAPI app for the household assistant (port 8080).
- `services/ops-bridge/app.py`: FastAPI app for the ops webhook bridge (port 8080 internal / 8085 external).
- `docker-compose.yml`: Full local stack composition (all services + their wiring).

**Configuration:**
- `services/nova-core/app/config.py`: Typed settings loaded from `.env`.
- `.env.example`: Template of all env vars (real values via Coolify, never committed).
- `ops/config.env.example`, `ops/secrets/infra.env.example`: Ops-script config templates.
- `Caddyfile`: Reverse proxy routing.

**Core Logic:**
- `services/nova-core/app/agent.py`: Agent loop — the heart of the assistant.
- `services/nova-core/app/tools/base.py`: Tool registration pattern used by all tool modules.
- `infra/postgres/init/01_schema.sql`: Data model.

**Testing:**
- Not detected. No test framework, test files, or test config found anywhere in the repo.

## Naming Conventions

**Files:**
- Python modules: `snake_case.py` (e.g., `agent.py`, `identity.py`).
- SQL init scripts: numeric-prefixed for ordering (`01_schema.sql`).
- Shell scripts: `snake_case.sh` verbs describing the action (`deploy.sh`, `heal.sh`, `triage.sh`).

**Directories:**
- Services live under `services/<service-name>/` with kebab-case names (`nova-core`, `ops-bridge`), each self-contained with its own `Dockerfile` and `requirements.txt`.
- Infra config grouped by concern under `infra/<concern>/` (`postgres/`, `vector/`).

**Python code conventions (observed):**
- `from __future__ import annotations` at the top of every module.
- Module-level docstring explaining the file's role, often referencing the build phase it belongs to (e.g., "STUB. Phase 5 replaces...").
- Settings/registries as module-level singletons (`settings`, `TOOLS`).
- Tool functions: `async def` with typed params, `user` param name reserved for injected household user identity.

## Where to Add New Code

**New household tool (e.g., calendar/email real implementation):**
- Implementation: edit the existing stub in `services/nova-core/app/tools/{calendar,email}.py`, keeping the `@tool(...)` name/description/parameters stable per `README.md`'s Phase 5 note.
- Register: no extra step needed — the `@tool` decorator auto-registers into `TOOLS`; ensure the module is imported by `services/nova-core/app/tools/__init__.py`.

**New channel adapter (e.g., WhatsApp webhook, Phase 4):**
- Add a new route under `services/nova-core/app/main.py` (per its own docstring, planned at `/webhooks/*`), translate the channel payload into a call to `run_agent()` from `agent.py`, resolving `user` via `identity.py` (extend with a new `user_from_<channel>()` function as needed).

**New API endpoint (dashboard, etc.):**
- Add to `services/nova-core/app/main.py`; follow the existing `/dashboard/*` stub pattern (return typed dict, TODO comment referencing the phase that wires real data).

**Database changes:**
- Add new tables/columns to `infra/postgres/init/01_schema.sql`. No migration framework exists — for a running (post-first-boot) database, changes must be applied manually or a migration tool must be introduced.

**New standalone service:**
- Create `services/<name>/` with its own `Dockerfile` + `requirements.txt` (mirror `ops-bridge/`'s single-file-app pattern for small services, or `nova-core/app/`'s package structure for larger ones), then wire it into `docker-compose.yml`.

**Ops/incident automation changes:**
- Add or edit scripts in `ops/`; shared helpers go in `ops/lib.sh`. Follow the existing verb-named `.sh` file convention.

**Tests (none exist yet):**
- No test directory or framework is present. When introducing tests, establish the convention explicitly (e.g., `services/nova-core/tests/` with pytest) since none currently exists to follow.

## Special Directories

**`ops/incidents/`:**
- Purpose: Local scratch space for incident-handling scripts.
- Generated: Yes (contents).
- Committed: No — only `.gitkeep` is tracked.

**`ops/secrets/`:**
- Purpose: Local secrets used by ops scripts (e.g., Forgejo tokens for `heal.sh`).
- Generated: No (manually populated from `infra.env.example`).
- Committed: No — only `.gitkeep` and the `.example` template are tracked; actual secrets are gitignored.

**`data/` (referenced in `docker-compose.yml`, not present in repo):**
- Purpose: Docker volume mount targets for `postgres`, `ollama`, `whisper`, `piper`, `caddy` persistent data.
- Generated: Yes, at runtime by Docker.
- Committed: No (not present in the tracked tree; created on first `docker compose up`).

---

*Structure analysis: 2026-07-11*
