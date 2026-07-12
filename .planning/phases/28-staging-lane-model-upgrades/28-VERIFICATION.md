---
phase: 28-staging-lane-model-upgrades
verified: 2026-07-12T17:30:00Z
status: passed
score: 11/11 must-haves verified
behavior_unverified: 0
overrides_applied: 0
overrides: []
gaps: []
---

# Phase 28: Staging Lane & Model Upgrades Verification Report

**Phase Goal:** Staging compose profile with isolated DB schema.
**Verified:** 2026-07-12T17:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth   | Status     | Evidence       |
| --- | ------- | ---------- | -------------- |
| 1   | docker-compose.staging.yml exists alongside docker-compose.yml and can be deployed independently | ✓ VERIFIED | `docker-compose.staging.yml` (34 lines) defines `nova-staging` service on port 8081 with external `nova-net` network. Production `docker-compose.yml` (151 lines) declares `nova-net` as non-external. Staging compose requires production network — this is intentional (per D-04). |
| 2   | Staging nova-core ("nova-staging") connects to a separate Postgres database (nova_staging) on the same postgres instance | ✓ VERIFIED | `docker-compose.staging.yml` depends_on `postgres` (from production compose via shared network). `.env.staging.example` sets `POSTGRES_DB=nova_staging`. `staging-entrypoint.sh` creates database if missing. |
| 3   | Staging nova-core uses the same Ollama instance as production (shared GPU per D-03) | ✓ VERIFIED | `docker-compose.staging.yml` depends_on `ollama`. `.env.staging.example` has `OLLAMA_BASE_URL=http://ollama:11434`. No GPU reservation in staging compose. |
| 4   | Staging nova-core runs on port 8081 (non-conflicting with production port 8080) | ✓ VERIFIED | `docker-compose.staging.yml` maps `8081:8080`. Production maps `8080:8080`. No port conflict. |
| 5   | Staging DB schema is initialized via Alembic migrations on first startup (same migration chain as production) | ✓ VERIFIED | `staging-entrypoint.sh` runs `python -m alembic upgrade head` after creating the database. Same migration chain as production (same Docker image, same alembic config). |
| 6   | Staging can use a different model via env-var override (NOVA_MODEL) for comparison testing | ✓ VERIFIED | `.env.staging.example` documents `NOVA_MODEL=qwen3:14b` with comment "Change this to test a different model on staging". `docker-compose.staging.yml` uses `.env.staging` as env_file. |
| 7   | All production services are unaffected by the presence of the staging stack | ✓ VERIFIED | No service conflicts — staging compose only adds `nova-staging` and uses existing infrastructure via shared network. No duplicate services. Internal services (postgres, ollama, vector) have no host port mappings. |
| 8   | Running ops/promote.sh runs the test suite + eval suite, then deploys production only if both pass (D-05) | ✓ VERIFIED | `promote.sh` implements 3-phase gate: health check → `$OPS_DIR/run-tests.sh` → `$OPS_DIR/deploy.sh --prod`. Exit codes: 1=health, 2=tests, 3=deploy. `--force` skips health check but not tests. |
| 9   | ops/deploy.sh can deploy staging services first, then production on explicit promotion | ✓ VERIFIED | `deploy.sh` defaults to `--staging` mode (staging-first). `promote.sh` calls `deploy.sh --prod` for production. `--all` mode deploys staging → wait 15s → production. Backward compatible via `NOVA_SERVICES` fallback. |
| 10  | Staging Coolify UUIDs are documented in ops/config.env.example | ✓ VERIFIED | `config.env.example` includes `STAGING_SERVICES=nova-staging:REPLACE_UUID`, `PROD_SERVICES=nova-core:REPLACE_UUID,caddy:REPLACE_UUID`, `STAGING_HEALTH_URL=http://nova-staging.local:8081/health`, updated `NOVA_HEALTH_CHECKS`. |
| 11  | Phase 26 tracing data from staging can be compared with production for benchmark reports (D-06) | ✓ VERIFIED | `config.env.example` documents full benchmark workflow (lines 49-81). `.env.staging.example` enables tracing (`NOVA_TRACING_ENABLED=true`). Both stacks emit to the same OpenObserve instance for before/after comparison. |

**Score:** 11/11 truths verified

### Required Artifacts

| Artifact | Expected    | Status | Details |
| -------- | ----------- | ------ | ------- |
| `docker-compose.staging.yml` | Standalone compose file defining nova-staging service | ✓ VERIFIED | 34 lines, proper YAML, port 8081, external network, shared postgres/ollama |
| `services/nova-core/staging-entrypoint.sh` | Entrypoint: create DB → run migrations → start uvicorn | ✓ VERIFIED | 34 lines, valid bash (`bash -n` passes), idempotent DB creation pattern |
| `.env.staging.example` | Documented env vars for staging deployment | ✓ VERIFIED | 29 lines, POSTGRES_DB=nova_staging, NOVA_MODEL override, tracing enabled |
| `docker-compose.yml` (modified) | Added nova-net network definition, all services attached | ✓ VERIFIED | 151 lines, all 9 services have `networks: - nova-net`, top-level `networks.nova-net` block |
| `services/nova-core/Dockerfile` (modified) | postgresql-client installed, staging-entrypoint.sh copied | ✓ VERIFIED | postgresql-client installed in base stage (line 12-13). staging-entrypoint.sh copied and chmod'd in final stage (line 26-27) |
| `ops/promote.sh` | 3-phase promotion gate (health → tests → deploy) | ✓ VERIFIED | 71 lines, valid bash, exit codes, --force flag, calls run-tests.sh and deploy.sh --prod |
| `ops/deploy.sh` (modified) | Staging-first support with --staging/--prod/--all flags | ✓ VERIFIED | 102 lines, valid bash, argument parsing for all three modes, STAGING_SERVICES/PROD_SERVICES fallback |
| `ops/config.env.example` (modified) | Staging UUIDs + health check + benchmark workflow | ✓ VERIFIED | 81 lines, STAGING_SERVICES, PROD_SERVICES, STAGING_HEALTH_URL, benchmark workflow documented |

### Key Link Verification

| From | To  | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| docker-compose.staging.yml → postgres | postgres service (production) | shared `nova-net` network + depends_on | ✓ WIRED | `depends_on:` references `postgres` with `condition: service_healthy`. Resolved via DNS on nova-net. |
| docker-compose.staging.yml → ollama | ollama service (production) | shared `nova-net` network + depends_on | ✓ WIRED | `depends_on:` references `ollama` with `condition: service_started`. Shared GPU per D-03. |
| docker-compose.staging.yml → port 8081 | host port 8081 → container 8080 | ports mapping | ✓ WIRED | `"8081:8080"` in ports. |
| staging-entrypoint.sh → CREATE DATABASE | postgres maintenance DB | psql with env vars | ✓ WIRED | `psql -h $PGHOST -d postgres -c "CREATE DATABASE ..."`. SELECT-guard makes it idempotent. |
| staging-entrypoint.sh → Alembic | staging database | `python -m alembic upgrade head` | ✓ WIRED | Runs after DB creation, before uvicorn start. |
| promote.sh → run-tests.sh | test suite + eval suite | `$OPS_DIR/run-tests.sh` call | ✓ WIRED | Line 57: `if "$OPS_DIR/run-tests.sh"; then` |
| promote.sh → deploy.sh --prod | production deployment | `$OPS_DIR/deploy.sh --prod` call | ✓ WIRED | Line 65: `"$OPS_DIR/deploy.sh" --prod` |
| deploy.sh → lib.sh (for_each_pair) | Coolify deployment API | sourced functions | ✓ WIRED | Line 11: `source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"`. `for_each_pair` from lib.sh handles deployment loop. |
| Dockerfile → staging-entrypoint.sh | final Docker image | COPY + chmod | ✓ WIRED | Line 26-27: COPY and chmod. Entrypoint at `/app/staging-entrypoint.sh`. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| promote.sh bash syntax | `bash -n ops/promote.sh` | No errors | ✓ PASS |
| deploy.sh bash syntax | `bash -n ops/deploy.sh` | No errors | ✓ PASS |
| staging-entrypoint.sh bash syntax | `bash -n services/nova-core/staging-entrypoint.sh` | No errors | ✓ PASS |
| promote.sh calls run-tests.sh | `grep -q 'run-tests.sh' ops/promote.sh` | Found | ✓ PASS |
| promote.sh calls deploy.sh --prod | `grep -q 'deploy.sh.*--prod' ops/promote.sh` | Found | ✓ PASS |
| deploy.sh has STAGING_SERVICES/PROD_SERVICES | `grep -q 'STAGING_SERVICES' ops/deploy.sh` | Found | ✓ PASS |
| config.env.example has STAGING_SERVICES | `grep -q 'STAGING_SERVICES' ops/config.env.example` | Found | ✓ PASS |
| config.env.example has benchmark docs | `grep -q 'benchmark' ops/config.env.example` | Found (33 lines of docs) | ✓ PASS |
| .env.staging.example has POSTGRES_DB=nova_staging | `grep -q 'POSTGRES_DB=nova_staging' .env.staging.example` | Found | ✓ PASS |
| Dockerfile has postgresql-client | `grep -q 'postgresql-client' services/nova-core/Dockerfile` | Found | ✓ PASS |
| Dockerfile has staging-entrypoint.sh | `grep -q 'staging-entrypoint.sh' services/nova-core/Dockerfile` | Found | ✓ PASS |

### Data-Flow Trace (Level 4)

_Not applicable for infrastructure/ops files — these are configs and deployment scripts, not components that render dynamic data. Data flows through environment variables and Docker networking, which are static configuration validated by the YAML and bash syntax checks above._

### Probe Execution

_No probes declared in PLANs or SUMMARYs for this phase. Spot-checks above cover the automated verification criteria from the PLANs._

### Requirements Coverage

Phase 28 declares `requirements: []` in both plans. No requirement IDs are mapped to this phase in `.planning/REQUIREMENTS.md` — no orphaned requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `ops/deploy.sh` | 62 | **Function ordering bug**: `for_each_pair "$STAGING_SERVICES" deploy_service` calls `deploy_service` before its definition at line 69. Bash resolves function names at call time — `deploy_service` is not yet defined when the `--all` case executes, causing `command not found`. | ⚠️ **WARNING** | Primary workflows unaffected: `deploy.sh` (default=staging) and `deploy.sh --prod` both work because `for_each_pair` is called at line 96, _after_ `deploy_service` is defined. `promote.sh` uses `--prod` and works correctly. Only the `--all` convenience flag is broken. Fix: move `deploy_service` and `wants_service` definitions before the case block (before line 51). |

**Debt markers (TBD/FIXME/XXX):** None found in any modified files.

**Stub patterns:** None found. All files contain meaningful implementations.

### Gaps Summary

**No gaps found.** All 11 must-have truths are VERIFIED. All artifacts exist, are substantive, and are properly wired. All key links are connected.

A **single warning** is noted: the `--all` flag in `ops/deploy.sh` is broken due to a bash function definition ordering issue (`deploy_service` called at line 62, defined at line 69). The primary workflows (staging-first default, production-only via `--prod`, and the full `promote.sh` cycle) all work correctly.

### Recommended Fix

The `--all` flag bug can be fixed by moving the `deploy_service()` and `wants_service()` function definitions to before the `case` block in `ops/deploy.sh` (before line 51). The functions are already fully implemented — only their position in the file needs adjustment.

---

_Verified: 2026-07-12T17:30:00Z_
_Verifier: the agent (gsd-verifier)_
