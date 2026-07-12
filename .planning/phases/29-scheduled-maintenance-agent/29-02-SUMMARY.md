---
phase: 29-scheduled-maintenance-agent
plan: 02
subsystem: maintenance
tags: [forgejo, pip-audit, openobserve, subprocess, httpx]
requires:
  - phase: 29-scheduled-maintenance-agent
    plan: 01
    provides: ForgejoClient, config settings, scheduler stubs, pip-audit
provides:
  - Nightly dependency scanner with pip list --outdated + pip-audit CVE scan
  - Automated branch creation, dep bumping, and test suite runner
  - Forgejo issue filing for both success and test-failure paths
  - Log-anomaly reviewer querying OpenObserve with heuristic detection
  - Log excerpt redaction (IPs, emails, paths) before issue filing
  - Dedup of log-anomaly issues (comment on existing instead of creating new)
affects:
  - 29-scheduled-maintenance-agent (Plan 29-03)
tech-stack:
  patterns:
    - Async subprocess execution via asyncio.create_subprocess_exec
    - git guard: abort if working tree is dirty
    - Forgejo token guard: file issues only if token is configured
    - OpenObserve SQL query pattern for log analysis
    - Heuristic anomaly detection (error count, spike ratio, CRITICAL/FATAL/traceback)
key-files:
  modified:
    - services/nova-core/app/maintenance/dependency_scanner.py
    - services/nova-core/app/maintenance/log_anomaly.py
  created:
    - services/nova-core/tests/test_maintenance.py
key-decisions:
  - All subprocess invocations use fixed argument lists (mitigation for T-29-06)
  - Log excerpts are redacted before inclusion in issue bodies (mitigation for T-29-07)
  - No auto-push or auto-merge: branches are local-only, human review required (T-29-08)
  - pip-audit exits non-zero when CVEs found; that is the reportable condition
  - Anomaly detection uses simple heuristics, not ML: min_count=3, spike_ratio=2.0, keyword matching
requirements-completed:
  - MAINT-01
  - MAINT-02
duration: 18min
completed: 2026-07-12
status: complete
---

# Phase 29 Plan 02: Dependency Scanner & Log-Anomaly Reviewer Summary

**Nightly dependency/CVE scanner with automated fix branches and test-gated issue filing, plus log-anomaly reviewer querying OpenObserve with heuristic detection and redacted Forgejo issues**

## Performance

- **Duration:** 18 min
- **Started:** 2026-07-12T14:13:00Z
- **Completed:** 2026-07-12T14:31:00Z
- **Tasks:** 3
- **Files modified:** 3 (2 replaced, 1 created)

## Accomplishments

- Dependency scanner detects outdated Python packages via `pip list --outdated`, CVEs via `pip-audit`, creates timestamped branch (`nova/dep-scan-YYYYMMDD-HHMMSS`), bumps deps in requirements.txt, runs test suite, and files Forgejo issues with results
- Tests-pass path: commits bumps, files success issue with package table, labels "maintenance,dependency-update", returns to original branch, deletes temp branch
- Tests-fail path: files "FAILED tests" issue with test output snippet, labels "maintenance,dependency-update,heal-failed", resets working tree with `git reset --hard`, returns to original branch
- Guards: dirty working tree (abort with warning), missing Forgejo token (console-only logging), git operation failures
- Log-anomaly reviewer queries OpenObserve's `/_search` API for last 24h, analyzes error/critical/fatal counts, computes baseline comparison from prior 24h window
- Heuristic detection: error count `>=3` and `>2x` baseline, any CRITICAL/FATAL lines, keyword matches for traceback/exception/unhandled/panic
- Log excerpt redaction: IPs, email addresses, and file paths replaced with `[REDACTED]` before issue filing
- Dedup: checks existing open issues with "log-anomaly" label; comments on existing rather than creating new
- 11 unit tests covering dep scan success, failure, dirty-tree guard, no-token guard; log anomaly spike, dedup, redaction, connection failure, critical-line detection

## Task Commits

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Nightly dependency/CVE scanner | `e114a30` |
| 2 | Log-anomaly reviewer | `e114a30` |
| 3 | Tests for both modules | `e114a30` |

## Files Created/Modified

- `services/nova-core/app/maintenance/dependency_scanner.py` — Full async implementation (replaced stub, +260 lines)
- `services/nova-core/app/maintenance/log_anomaly.py` — Full async implementation (replaced stub, +260 lines)
- `services/nova-core/tests/test_maintenance.py` — 11 unit tests (new)

## Decisions Made

- All subprocess calls use `asyncio.create_subprocess_exec` with 120s timeout — never blocking `subprocess.run()` in async context
- Anomaly detection uses simple heuristic thresholds (MIN_ERROR_COUNT=3, SPIKE_RATIO=2.0) as module-level constants for easy tuning
- OpenObserve query format uses the `/_search` HTTP API with SQL-like queries — simplest approach that returns log counts by level
- Redaction regex patterns cover IPv4 addresses, RFC-5322 emails, and common path prefixes (/Users/, /home/, /app/)
- Dependency bump only updates requirements.txt via regex replacement — does not handle pyproject.toml or other config formats (deferred to future enhancement)

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- The `test_dep_scan_tests_fail` mock sequence initially included `git add` and `git commit` steps that don't execute in the failure path. Fixed mock to match actual code flow (no commit before test in failure path).

## Verification Results

1. ✅ `python -m pytest services/nova-core/tests/test_maintenance.py -x -v -k "dep"` — all 5 dep scan tests pass
2. ✅ `python -m pytest services/nova-core/tests/test_maintenance.py -x -v -k "log_anomaly"` — all 6 log-anomaly tests pass
3. ✅ `python -m pytest services/nova-core/tests/test_maintenance.py -x -v` — all 11 tests pass
4. ✅ `python -c "from app.maintenance.dependency_scanner import run_dependency_scan; from app.maintenance.log_anomaly import run_log_anomaly_review; print('OK')"` — both modules import cleanly

## Next Phase Readiness

- Plan 29-03 (backup verification, trend reporter) can now be implemented and tested using the same patterns
- ForgejoClient pattern, subprocess pattern, and test infrastructure proven in this plan
