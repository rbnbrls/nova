---
phase: 29-scheduled-maintenance-agent
plan: 03
subsystem: maintenance
tags: [forgejo, docker, postgres, nvidia-smi, shutil, subprocess]
requires:
  - phase: 29-scheduled-maintenance-agent
    plan: 01
    provides: ForgejoClient, config settings, Docker socket mount, scheduler stubs
provides:
  - Nightly backup verification via ephemeral scratch Postgres container
  - Weekly disk/VRAM/GPU/Postgres trend report with threshold alerts
  - Delta comparison against prior readings with week-over-week change tracking
  - Graceful degradation in all failure modes (no docker, no GPU, no token)
affects: []
tech-stack:
  patterns:
    - Ephemeral scratch container lifecycle (docker run → pg_isready → restore → query → stop → rm)
    - Metric collection via shutil.disk_usage, nvidia-smi subprocess, pg_database_size()
    - Trend data persistence via HTML comment JSON in Forgejo issue body
    - Machine-parseable trend tracking for week-over-week comparisons
key-files:
  modified:
    - services/nova-core/app/maintenance/backup_verifier.py
    - services/nova-core/app/maintenance/trend_reporter.py
    - services/nova-core/tests/test_maintenance.py
key-decisions:
  - Scratch container uses postgres:16-alpine (not pgvector) for faster startup
  - Trend data stored as HTML comment JSON in issue body for machine parsing
  - Threshold violations generate WARNING/CRITICAL banners in issue bodies
  - All Docker operations use timeouts; nvidia-smi failure is graceful (N/A, not crash)
  - Container always cleaned up on success OR failure (try/finally pattern)
requirements-completed:
  - MAINT-03
  - MAINT-04
duration: 15min
completed: 2026-07-12
status: complete
---

# Phase 29 Plan 03: Backup Verification & Trend Reporter Summary

**Nightly Postgres dump verification via ephemeral Docker scratch container with integrity queries, plus weekly system trend report with disk, GPU/VRAM, and Postgres metrics, threshold alerts, and delta comparisons**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-12T14:31:00Z
- **Completed:** 2026-07-12T14:46:00Z
- **Tasks:** 3
- **Files modified:** 3 (2 replaced, 1 appended)

## Accomplishments

- Backup verifier finds latest dump file matching pattern, restores into ephemeral `postgres:16-alpine` scratch container, runs `SELECT count(*)` on tables and columns, queries `pg_stat_user_tables` for row counts, then stops and removes the container
- Success path: files issue with "backup verification OK" title, body includes table count, column count, row counts per table, dump size
- Failure paths: no dump files, empty dump file (0 bytes), restore failure, docker unavailable — each produces appropriate Forgejo issue or console-only warning
- Stale container cleanup: retries docker run after `docker rm -f` if named container already exists
- Trend reporter collects disk usage (`shutil.disk_usage`), GPU/VRAM (`nvidia-smi --query-gpu`), and Postgres size (`pg_database_size()`)
- Threshold alerts: disk >80% (WARNING), >90% (CRITICAL); VRAM >85% (WARNING), >95% (CRITICAL); GPU >80°C (WARNING); week-over-week delta >10% (highlighted)
- Trend data embedded as HTML comment JSON in issue body (`<!-- trend-data: {...} -->`) for machine-parseable week-over-week comparison
- Existing trend issues: comments appended with delta section showing changes from prior readings
- Graceful degradation across all failure modes: no docker socket → log warning; no nvidia-smi → "N/A" metrics; no forgejo token → console-only logging; Postgres query failure → "N/A"
- 11 new tests appended to test_maintenance.py (22 total across Plan 2 + 3)

## Task Commits

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Backup verification module | `8224831` |
| 2 | Disk/VRAM trend reporter | `8224831` |
| 3 | Tests for both modules | `8224831` |

## Files Created/Modified

- `services/nova-core/app/maintenance/backup_verifier.py` — Full async implementation (replaced stub, +240 lines)
- `services/nova-core/app/maintenance/trend_reporter.py` — Full async implementation (replaced stub, +300 lines)
- `services/nova-core/tests/test_maintenance.py` — 11 new tests appended (22 total)

## Decisions Made

- Scratch container uses `postgres:16-alpine` for faster download/start instead of `pgvector/pgvector:pg16` (production uses pgvector, but scratch doesn't need vector extension)
- Trend data stored as HTML comment JSON at the bottom of the issue body — parseable by the next run's `_parse_previous_readings()` function, invisible when rendered to humans
- Threshold constants are module-level (`DISK_WARN_PCT = 80`, `DISK_CRIT_PCT = 90`, etc.) for easy tuning without code changes
- Container cleanup runs in `except` as well as success paths — ensuring no orphaned containers even on failure
- `nvidia-smi` failure doesn't block the report: VRAM/GPU metrics show "N/A", disk and Postgres data still filed

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- `_restore_dump()` calls `open(dump_path, "r")` which fails when the test dump path doesn't exist on filesystem. Fixed by adding `patch("builtins.open", MagicMock())` to tests that exercise the restore path.
- `shutil.disk_usage()` returns a named tuple, but mocking without a proper return value causes MagicMock attributes that can't be compared to integers. Fixed by explicitly creating `MagicMock()` instances with real numeric `.total`, `.used`, `.free` attributes.
- `AsyncMock` for `get_pool()` requires proper `acquire().__aenter__()` chain to avoid `RuntimeWarning` about unawaited coroutines. Added `mock_pool.acquire.return_value.__aexit__ = AsyncMock()`.

## Verification Results

1. ✅ `python -m pytest services/nova-core/tests/test_maintenance.py -x -v -k "backup"` — all 5 backup verify tests pass
2. ✅ `python -m pytest services/nova-core/tests/test_maintenance.py -x -v -k "trend"` — all 6 trend reporter tests pass
3. ✅ `python -m pytest services/nova-core/tests/test_maintenance.py -x -v` — all 22 tests pass
4. ✅ `python -c "from app.maintenance.backup_verifier import run_backup_verification; from app.maintenance.trend_reporter import run_trend_report; print('OK')"` — both modules import cleanly

## Next Phase Readiness

- All 4 maintenance jobs fully implemented and tested
- ForgejoClient, subprocess pattern, and async patterns proven across all modules
- Phase 29 complete — all success criteria met
