# Phase 29 Context: Scheduled Maintenance Agent

## Source
ROADMAP.md Phase 29 goal + success criteria.

## Decisions

### Scope
All 4 success criteria in scope for this phase:
1. Nightly dependency/CVE bumps with tested fix branches
2. Log-anomaly review (OpenObserve → Forgejo issues)
3. Backup verification (Postgres dump → scratch container query)
4. Disk/VRAM trend reporting as periodic issue

### Implementation Approach
- Run as a scheduled job via the existing scheduler infrastructure (apscheduler)
- Results filed as Forgejo issues using the ops-bridge `heal.sh` patterns
- Merge requires human approval — automated branches only, never auto-merge
- Follow Phase 9 (ops-bridge / heal.sh) patterns for Forgejo API interaction

### Nightly Dependency Bumps
- Check pyproject.toml / requirements files for outdated deps
- Create a fix branch with bumps, run tests, if green → file Forgejo PR
- CVE scan using `pip-audit` or similar

### Log-Anomaly Review
- Query OpenObserve for error spikes, unusual patterns
- File structured issues with log excerpts (redacted)
- Run after nightly log rotation

### Backup Verification
- Take latest Postgres dump from backup location
- Restore into temporary scratch container
- Run a SELECT query to verify data integrity
- Report success/failure

### Disk/VRAM Trends
- Collect disk usage, VRAM usage, GPU temperature
- Compare against prior readings
- File periodic trend report (weekly)

## Deferred Ideas
None.
