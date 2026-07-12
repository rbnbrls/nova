---
phase: 28-staging-lane-model-upgrades
plan: 01
subsystem: infra
tags: [docker, compose, staging, postgres, ollama, network]
requires: []
provides:
  - Shared nova-net Docker network connecting all production services
  - docker-compose.staging.yml for isolated deployment lane
  - Staging entrypoint that creates DB, runs migrations, starts uvicorn
  - .env.staging.example template with separate database and model override
affects: [phase 28 plan 02, phase 26 tracing benchmark workflow]
tech-stack:
  added: [postgresql-client (apt package)]
  patterns:
    - External Docker network pattern for multi-compose service discovery
    - Staging entrypoint script pattern (create DB → migrate → start)
    - Separate compose profile for deployment lane isolation
key-files:
  created:
    - docker-compose.staging.yml
    - services/nova-core/staging-entrypoint.sh
    - .env.staging.example
  modified:
    - docker-compose.yml
    - services/nova-core/Dockerfile
key-decisions:
  - "Shared nova-net bridge network: all production + staging containers discover each other by DNS name"
  - "Staging entrypoint uses psql to CREATE DATABASE IF NOT EXISTS pattern — idempotent, safe on restart"
  - "postgresql-client installed in Dockerfile base stage so both tester and final stage can use it"
  - "Internal-only services (postgres, ollama, vector) kept without host ports — prevents accidental host-level DB access"
  - "Staging uses same Docker image as production — only entrypoint and env differ"
patterns-established:
  - "Staging overlay pattern: external network on shared bridge, env-based config differences"
status: complete
duration: 18min
completed: 2026-07-12
---

# Phase 28 Plan 01: Staging Compose Profile Summary

**Shared nova-net Docker network, docker-compose.staging.yml with isolated nova-staging service, staging entrypoint, and env template for model comparison testing**

## Performance

- **Duration:** 18 min
- **Started:** 2026-07-12T15:11:04Z
- **Completed:** 2026-07-12T15:29:00Z
- **Tasks:** 3
- **Files modified:** 6 (5 new, 1 modified)

## Accomplishments

- Created `nova-net` shared bridge network — all production services (nova-core, postgres, ollama, whisper, piper, vector, ops-bridge, radicale, caddy) attached. Internal-only services (postgres, ollama, vector) have no host port exposure.
- Created `docker-compose.staging.yml` — standalone compose profile defining `nova-staging` service on port 8081, connecting to shared postgres and ollama via external `nova-net` network.
- Created `services/nova-core/staging-entrypoint.sh` — bash script that creates `nova_staging` database if missing, runs Alembic migrations, then starts uvicorn. Idempotent and safe on container restart.
- Updated `services/nova-core/Dockerfile` — installs `postgresql-client` in base stage (needed by psql), copies staging-entrypoint.sh in final stage.
- Created `.env.staging.example` — documents `POSTGRES_DB=nova_staging` (D-02), `NOVA_MODEL` override (D-03), tracing defaults (D-06).

## Task Commits

Each task was committed atomically:

1. **Task 1: Add nova-net network and update docker-compose.yml** - `8171608` (feat)
2. **Task 2: Create docker-compose.staging.yml** - `9bbe99a` (feat)
3. **Task 3: Create entrypoint, update Dockerfile, create .env.staging.example** - `c97cec9` (feat)

## Files Created/Modified

- `docker-compose.yml` - Added `networks.nova-net` block, attached all 9 services to the shared network
- `docker-compose.staging.yml` - New: standalone compose file for nova-staging service (port 8081, external network, shared postgres/ollama)
- `services/nova-core/staging-entrypoint.sh` - New: database creation → migrations → uvicorn
- `services/nova-core/Dockerfile` - Added postgresql-client install (base stage) and staging-entrypoint.sh copy (final stage)
- `.env.staging.example` - New: staging env template with separate DB and model override

## Decisions Made

- **Shared bridge network** — `nova-net` with `external: false` in production and `external: true` in staging. This lets staging access postgres and ollama without re-declaring them, simplifying the staging compose file.
- **Idempotent DB creation** — The entrypoint uses `SELECT 1 FROM pg_database WHERE datname = ...` before `CREATE DATABASE`, making restarts safe. This mitigates T-28-03 (tampering).
- **postgresql-client in base stage** — Installed in the `FROM base` stage so both the `tester` and final `FROM base` stages have psql available. The tester stage doesn't need it, but including it avoids a separate install.
- **No GPU reservation for staging** — Staging shares production's ollama via DNS (Per D-03). No `deploy.resources` needed.
- **No duplicated services** — postgres, ollama, whisper, piper, vector, ops-bridge, radicale, caddy are NOT declared in docker-compose.staging.yml — they're accessed via the shared `nova-net` network.

## Deviations from Plan

None — plan executed exactly as written.

## Threat Register Compliance

| Threat ID | Disposition | Status |
|-----------|-------------|--------|
| T-28-01 | mitigate | Mitigated — separate `nova_staging` database on same Postgres instance |
| T-28-02 | mitigate | Accepted — shared ollama GPU contention monitored via Phase 26 tracing |
| T-28-03 | mitigate | Mitigated — entrypoint is idempotent; fixed database name prevents SQL injection |
| T-28-04 | accept | Accepted — shared network on trusted Nova VM |
| T-28-SC | accept | Accepted — postgresql-client from official Debian repos |

## Issues Encountered

None — all tasks executed cleanly.

## Next Phase Readiness

- Staging infrastructure foundation complete — `docker-compose.staging.yml` ready for deployment
- Plan 28-02 (promotion gate and staging-first workflow) can use the nova-staging health endpoint at port 8081
- After both plans deployed on the Nova VM: run `docker compose -f docker-compose.staging.yml up -d` alongside production

---
*Phase: 28-staging-lane-model-upgrades*
*Plan: 01*
*Completed: 2026-07-12*
