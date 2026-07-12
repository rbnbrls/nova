---
phase: 29-scheduled-maintenance-agent
plan: 01
subsystem: maintenance
tags: [forgejo, apscheduler, pydantic-settings, docker, httpx]
requires: []
provides:
  - ForgejoClient with issue CRUD, label management, and caching
  - maintenance/ subpackage with 4 job stubs
  - Config fields for Forgejo URL/repo/token and maintenance toggles
  - APScheduler cron job registration for all 4 maintenance jobs
  - Docker volume mounts for docker.sock (ro) and backup directory
  - pip-audit dependency for CVE scanning
affects:
  - 29-scheduled-maintenance-agent (all subsequent plans)
tech-stack:
  added: [pip-audit==2.7.3]
  patterns:
    - Forgejo API client pattern (httpx + token-auth + label caching)
    - Maintenance subpackage pattern (stubs → real impl in later plans)
    - Feature-toggled async scheduler functions
key-files:
  created:
    - services/nova-core/app/forgejo.py
    - services/nova-core/app/maintenance/__init__.py
    - services/nova-core/app/maintenance/dependency_scanner.py
    - services/nova-core/app/maintenance/log_anomaly.py
    - services/nova-core/app/maintenance/backup_verifier.py
    - services/nova-core/app/maintenance/trend_reporter.py
    - services/nova-core/tests/test_forgejo.py
  modified:
    - services/nova-core/app/config.py
    - services/nova-core/app/scheduler.py
    - services/nova-core/app/main.py
    - docker-compose.yml
    - .env.example
    - services/nova-core/requirements.txt
key-decisions:
  - ForgejoClient patterned after ops-bridge app.py (httpx + token + label resolution)
  - All maintenance jobs gated by maintenance_enabled toggle plus per-job toggles
  - Docker socket mounted read-only, backup dir mounted read-only
  - pip-audit added to requirements.txt (CVE scanning; installed via Docker build)
  - Cron schedules: dep scan 2AM, log anomaly 3AM, backup verify 4AM daily, trend report 5AM Sunday
patterns-established:
  - "Maintenance subpackage: __init__.py imports stub modules with # noqa: F401"
  - "Async job guard: if not settings.<toggle>: return — before calling module function"
  - "ForgejoClient: _resolve_label_ids caches label name→id mappings across calls"
requirements-completed:
  - MAINT-FRAMEWORK
duration: 15min
completed: 2026-07-12
status: complete
---

# Phase 29 Plan 01: Foundation Summary

**Forgejo API client, maintenance subpackage stubs, config settings, Docker mounts, and APScheduler job wiring — the shared infrastructure for all 4 maintenance jobs**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-12T13:57:30Z
- **Completed:** 2026-07-12T14:12:30Z
- **Tasks:** 3
- **Files modified:** 13 (7 created, 6 modified)

## Accomplishments

- ForgejoClient class with full issue CRUD, label management, and cached label-to-ID resolution
- 10 unit tests for ForgejoClient covering issue creation (plain + with labels), commenting, closing, label management, error handling, and ID caching
- Pydantic Settings fields for Forgejo URL/repo/token and all maintenance feature toggles
- `maintenance/` subpackage with 4 async stub modules (dependency_scanner, log_anomaly, backup_verifier, trend_reporter) that log "not yet implemented"
- 4 async scheduler functions in scheduler.py gated by per-job feature toggles
- 4 APScheduler cron jobs registered in main.py lifespan, wrapped by `maintenance_enabled` guard
- Docker socket (read-only) and backup directory volume mounts added to nova-core service
- `FORGEJO_*` and `MAINTENANCE_*` environment variables documented in `.env.example`
- pip-audit==2.7.3 added to requirements.txt

## Task Commits

| Task | Description | Commit |
|------|-------------|--------|
| 1 | ForgejoClient module + config settings + unit tests | `f5ef4b1` |
| 2 | Maintenance subpackage with stub modules + scheduler wiring | `26e84b5` |
| 3 | Docker mounts, env vars, and pip-audit dependency | `ec2b979` |

## Files Created/Modified

- `services/nova-core/app/forgejo.py` — ForgejoClient class (new)
- `services/nova-core/app/config.py` — Added 11 new Settings fields
- `services/nova-core/tests/test_forgejo.py` — 10 unit tests (new)
- `services/nova-core/app/maintenance/__init__.py` — Subpackage init (new)
- `services/nova-core/app/maintenance/dependency_scanner.py` — Stub job (new)
- `services/nova-core/app/maintenance/log_anomaly.py` — Stub job (new)
- `services/nova-core/app/maintenance/backup_verifier.py` — Stub job (new)
- `services/nova-core/app/maintenance/trend_reporter.py` — Stub job (new)
- `services/nova-core/app/scheduler.py` — 4 new async functions
- `services/nova-core/app/main.py` — 4 new APScheduler job registrations
- `docker-compose.yml` — Volume mounts for docker.sock and backups
- `.env.example` — New FORGEJO_* and MAINTENANCE_* env vars
- `services/nova-core/requirements.txt` — Added pip-audit==2.7.3

## Decisions Made

- ForgejoClient follows the same httpx + token-auth + label-resolution pattern as `services/ops-bridge/app.py` for consistency
- All maintenance jobs are gated by a master toggle (`maintenance_enabled`) plus individual per-job toggles for fine-grained control
- Docker socket mounted read-only (`:ro`) to mitigate privilege escalation (threat T-29-02)
- Cron schedules staggered to avoid resource contention: dep scan at 2AM, log anomaly at 3AM, backup verify at 4AM daily, trend report at 5AM Sunday
- pip-audit listed in requirements.txt but installed at Docker build time (per threat model T-29-SC, human verification of package legitimacy would gate the actual deployment)

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- AsyncMock HTTPX context manager mock required explicit `__aenter__` / `__aexit__` setup to match the `async with httpx.AsyncClient(...) as client:` pattern used in `_api()`. Resolved with a `_make_mock_async_client` helper that wires the async context manager correctly.

## Verification Results

1. ✅ `python -m pytest services/nova-core/tests/test_forgejo.py -x -v` — all 10 tests pass
2. ✅ `python -c "from app.scheduler import run_maintenance_dep_scan; print('OK')"` — imports OK
3. ✅ `python -c "import pip_audit; print(pip_audit.__version__)"` — pip-audit 2.7.3 available
4. ✅ `docker-compose.yml` has nova-core volume mounts for docker.sock (ro) and backups (ro)
5. ✅ `.env.example` has all FORGEJO_* and MAINTENANCE_* variables documented

## Next Phase Readiness

- Foundation is ready for Plans 29-02 (dependency scanner + log anomaly) and 29-03 (backup verification + trend reporter)
- ForgejoClient is tested and importable from scheduler job modules
- All 4 stub modules can be replaced with real implementations
