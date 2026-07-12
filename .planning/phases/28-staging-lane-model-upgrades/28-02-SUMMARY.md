---
phase: 28-staging-lane-model-upgrades
plan: 02
subsystem: ops
tags: [bash, scripting, ci-cd, deployment, coolify, staging, promotion]
requires:
  - phase: 28-staging-lane-model-upgrades
    plan: 01
    provides: docker-compose.staging.yml and nova-staging service
provides:
  - ops/promote.sh — 3-phase promotion gate (health → tests/evals → deploy)
  - Updated ops/deploy.sh with --staging/--prod/--all flags
  - Updated ops/config.env.example with staging UUIDs and benchmark workflow
affects: [future deployment operations, Coolify configuration]
tech-stack:
  added: []
  patterns:
    - Three-phase promotion gate with distinct exit codes
    - Staging-first deployment with explicit production promotion
    - Env-var-based service list selection with NOVA_SERVICES fallback
key-files:
  created:
    - ops/promote.sh
  modified:
    - ops/deploy.sh
    - ops/config.env.example
key-decisions:
  - "promote.sh calls deploy.sh --prod for clean separation of concerns"
  - "Staging-first default: deploy.sh without args deploys staging only"
  - "NOVA_SERVICES fallback ensures backward compatibility if STAGING/PROD_SERVICES are not set"
  - "Distinct exit codes (1=health, 2=tests, 3=deploy) for CI pipeline integration"
patterns-established:
  - "Staging-first deployment pattern: staging by default, production via --prod or promote.sh"
status: complete
duration: 12min
completed: 2026-07-12
---

# Phase 28 Plan 02: Promotion Gate & Staging-First Deployment Summary

**Create ops/promote.sh promotion gate, update ops/deploy.sh for staging-first workflow, document staging config and model benchmark workflow**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-12T15:29:00Z
- **Completed:** 2026-07-12T15:41:00Z
- **Tasks:** 3
- **Files modified:** 3 (1 new, 2 modified)

## Accomplishments

- Created `ops/promote.sh` — 3-phase promotion gate: verifies staging health (with retry), runs test suite + evals, deploys production only if all gates pass. Distinct exit codes (1=health, 2=tests, 3=deploy) for CI integration. `--force` flag skips health check.
- Updated `ops/deploy.sh` with `--staging` (default), `--prod`, and `--all` flags. `--all` mode deploys staging first, waits 15s for stability, then deploys production. Backward compatible via `NOVA_SERVICES` fallback when `STAGING_SERVICES`/`PROD_SERVICES` is not set.
- Updated `ops/promote.sh` to call `deploy.sh --prod` for clean separation.
- Updated `ops/config.env.example` with `STAGING_SERVICES`, `PROD_SERVICES`, `STAGING_HEALTH_URL`, updated `NOVA_HEALTH_CHECKS` including staging, and documented the full model benchmarking workflow using Phase 26 tracing (D-06).
- **Per D-04:** Manual promotion via ops/promote.sh.
- **Per D-05:** Tests + evals gate via run-tests.sh failure propagation.
- **Per D-06:** Benchmark workflow documented using Phase 26 tracing for before/after comparison.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create ops/promote.sh promotion gate** - `9eb2e76` (feat)
2. **Task 2: Update ops/deploy.sh for staging-first support** - `2ca58cd` (feat)
3. **Task 3: Update ops/config.env.example with staging config** - `eacf997` (feat)

## Files Created/Modified

- `ops/promote.sh` — New: 3-phase promotion gate (health → tests/evals → deploy) with exit codes and --force flag
- `ops/deploy.sh` — Modified: argument parsing for --staging/--prod/--all flags, STAGING_SERVICES/PROD_SERVICES env vars with NOVA_SERVICES fallback, staging-first deployment in --all mode
- `ops/config.env.example` — Modified: added STAGING_SERVICES, PROD_SERVICES, STAGING_HEALTH_URL, updated NOVA_HEALTH_CHECKS, documented model benchmarking workflow

## Decisions Made

- **Staging-first default** — `deploy.sh` without args deploys staging only, reflecting the staging-first philosophy (D-04). Production requires an explicit `--prod` flag or the `promote.sh` gate.
- **promote.sh calls deploy.sh --prod** — Keeps separation of concerns: promote.sh is the gate, deploy.sh is the execution engine.
- **NOVA_SERVICES fallback** — If `STAGING_SERVICES` or `PROD_SERVICES` is not set in config.env, the script falls back to `NOVA_SERVICES` for backward compatibility.
- **Distinct exit codes** — 1=health check fail, 2=test/evals fail, 3=deploy fail. Enables CI systems to distinguish failure modes.
- **15s staging→production wait in --all mode** — Gives staging containers time to stabilize before production deploys. Mitigates T-28-08 (tampering in --all mode).
- **--force flag** — Skips health check but NOT the test gate. Health checks can fail for transient reasons; the test gate is never bypassed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added execute permission to promote.sh**
- **Found during:** Task 1 (pre-commit)
- **Issue:** promote.sh was created without execute permission, but all other ops scripts (deploy.sh, pipeline.sh, lib.sh) are executable
- **Fix:** `chmod +x ops/promote.sh`
- **Files modified:** ops/promote.sh
- **Verification:** `ls -la ops/promote.sh` shows `-rwxr-xr-x`
- **Committed in:** `9eb2e76` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Minor — promote.sh needed execute permission to be runnable like other ops scripts. No scope creep.

## Threat Register Compliance

| Threat ID | Disposition | Status |
|-----------|-------------|--------|
| T-28-05 | mitigate | Mitigated — promote.sh reads env vars, runs tests, calls deploy.sh. No state mutation beyond deploying production |
| T-28-06 | mitigate | Mitigated — requires Coolify API credentials; only operators with VM access can run promote.sh |
| T-28-07 | accept | Accepted — STAGING_HEALTH_URL configurable on same trusted VM |
| T-28-08 | mitigate | Mitigated — FAILED flag ensures failed staging blocks production in --all mode |
| T-28-SC | accept | Accepted — no new package dependencies (curl and jq already required) |

## Issues Encountered

None — all tasks executed cleanly.

## Next Phase Readiness

- Staging-first deployment workflow ready for Coolify configuration
- After Coolify deployment: Nova VM operator configures `.env.staging` with real secrets, sets up staging UUIDs in `ops/config.env`
- Model benchmark workflow documented — ready for Phase 26 tracing comparison
- Next ops scripts can build on `promote.sh` pattern for automated CI pipelines

---
*Phase: 28-staging-lane-model-upgrades*
*Plan: 02*
*Completed: 2026-07-12*
