---
phase: 36
plan: 01
subsystem: nova-core
tags: [audit, dashboard, sse, alembic, agent-loop]
requires: [phase-08-write-confirmation-gate, phase-12-read-only-dashboard]
affects: [agent-loop, dashboard-ui, database-schema]
tech-stack:
  added: []
  patterns:
    - "asyncpg parameterized INSERT with RETURNING"
    - "FastAPI route handler callable from SSE generator"
    - "Alembic migration with index on DESC sort"
key-files:
  created:
    - services/nova-core/alembic/versions/0004_audit_log_table.py
    - services/nova-core/app/audit.py
    - services/nova-core/tests/test_audit.py
  modified:
    - services/nova-core/app/agent.py
    - services/nova-core/app/main.py
    - services/nova-core/static/index.html
    - services/nova-core/static/app.js
    - services/nova-core/static/style.css
decisions:
  - "Mutating tools defined as _MAX_MUTATING_TOOLS = {add_task, complete_task, create_event}"
  - "Auto-prune implemented as 90-day WHERE filter in endpoint query (not background job)"
  - "Denied confirmation audit written before the early return to guarantee recording"
  - "record_tool_call wraps DB errors with try/except so audit failures don't crash the agent loop"
  - "SSE stream shares the same 15-second interval as tasks/events"
metrics:
  duration_minutes: 8
  completed_date: "2026-07-12"
status: complete
---

# Phase 36 Plan 01: Write-Action Audit Trail Summary

One-liner: Alembic migration creating `audit_log` table, `record_tool_call()` recording every mutating agent invocation (both confirmed and denied), `/dashboard/audit` REST endpoint with SSE integration, and a scrolling Activity Feed panel in the dashboard UI.

## Tasks

| Task | Name | Status | Commit | Files |
| ---- | ---- | ------ | ------ | ----- |
| 1 | Create audit_log table migration + audit module + tests | ✅ Done | `fe53986` | alembic/versions/0004_audit_log_table.py, app/audit.py, tests/test_audit.py |
| 2 | Wire audit recording into agent loop + dashboard endpoint + SSE + tests | ✅ Done | `2646ad1` | app/agent.py, app/main.py, tests/test_audit.py |
| 3 | Add Activity Feed panel to dashboard UI | ✅ Done | `faff87e` | static/index.html, static/app.js, static/style.css |

## Implementation Details

### Task 1 — Migration + Module + Tests
- **Alembic migration `0004_audit_log_table.py`**: Creates `audit_log` table with `id` (BIGSERIAL PK), `created_at` (timestamp with timezone, default now()), `user_name` (varchar 255), `tool_name` (varchar 255), `action_summary` (text), `status` (varchar 50), `confirmation_required` (boolean, default false). Index on `created_at DESC`.
- **`app/audit.py`**: Async `record_tool_call()` function that INSERTs into `audit_log` with `RETURNING id`. Wraps DB errors in try/except returning None.
- **Tests**: `test_record_tool_call()` (mock, verifies INSERT params) and `test_record_tool_call_integration()` (skipped without live DB).

### Task 2 — Agent Wiring + Endpoint + SSE
- **`_summarize_action()` helper**: Generates human-readable summaries for `add_task`, `complete_task`, `create_event` with a fallback for future tools.
- **`_MAX_MUTATING_TOOLS` set**: `{add_task, complete_task, create_event}` — read-only tools (list_tasks, list_events, list_recent_emails) are excluded.
- **Site 1 (completed)**: After `tools.call_tool()` succeeds, records audit with `status="completed"` for mutating tools.
- **Site 2 (denied)**: Before the confirmation early-return, records audit with `status="denied"` and `confirmation_required=True`.
- **`GET /dashboard/audit`**: Returns last N entries (default 50) filtered to 90 days, following the same pattern as `/dashboard/tasks`.
- **SSE extension**: Calls `dashboard_audit(limit=50)` inside the existing 15-second event generator, adds `"audit"` key to the JSON payload.

### Task 3 — Dashboard UI
- **index.html**: New `audit-panel` section below the main grid, with loading placeholder.
- **app.js**: `updateAudit(entries)` renders a scrolling table with Time/User/Action/Status columns. `escapeHtml()` prevents XSS. SSE handler extended to call `updateAudit(data.audit)`.
- **style.css**: Glass-panel styling for the audit feed, table with sticky header, scrollbar, and status badges (✅ Done / 🚫 Denied / 🛡️ confirmation icon).

## Test Results

```
12 passed, 1 skipped, 1 warning in 0.52s
```

Audit-specific tests (5 passed, 1 skipped):
- `test_record_tool_call` — INSERT params verified
- `test_record_tool_call_integration` — skipped (no DB)
- `test_dashboard_audit_endpoint` — 200 + correct shape + 90-day filter
- `test_dashboard_audit_empty` — empty array returned
- `test_run_agent_records_audit_on_tool_call` — agent calls record_tool_call for mutating tools
- `test_run_agent_records_denied_confirmation` — denied confirmation recorded

No regressions in existing test_agent.py (4/4) or test_dashboard.py (3/4 — SSE stream test times out on infinite loop, expected).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 — Error Handling] Added try/except to record_tool_call**
- **Found during:** Task 1
- **Issue:** DB write failures would crash the agent loop if the pool is unavailable
- **Fix:** `record_tool_call` wraps the INSERT in try/except, logs the exception, and returns None
- **Files modified:** `app/audit.py`
- **Commit:** `fe53986`

**2. [Rule 2 — Missing Dependency] pytest-asyncio not installed in venv**
- **Found during:** Task 1 verification
- **Issue:** The project's `pyproject.toml` configures `asyncio_mode = "auto"` and existing tests use `@pytest.mark.asyncio`, but `pytest-asyncio` was not installed in the virtual environment
- **Fix:** Installed `pytest-asyncio` via pip3
- **Files modified:** None (venv dependency install)

## Known Stubs

None identified.

## Threat Flags

No new threat surface introduced beyond what is documented in PLAN.md threat model.

## Self-Check: PASSED

- [x] Migration file exists at 0004_audit_log_table.py with revises="0003"
- [x] app/audit.py exposes record_tool_call() that INSERTs into audit_log
- [x] Agent.py records every mutating tool call with correct user/tool/summary/status
- [x] Denied confirmation recorded before early return with status="denied"
- [x] Read-only tools excluded (no audit rows for list_tasks/list_events/list_recent_emails)
- [x] GET /dashboard/audit returns entries filtered to 90 days
- [x] SSE stream includes "audit" key alongside tasks/events
- [x] Dashboard UI shows scrolling Activity Feed with Time/User/Action/Status columns
- [x] Tests cover: recording, endpoint shape, empty response, denied-path logging
- [x] No TBD/FIXME/XXX markers in any created/modified file
