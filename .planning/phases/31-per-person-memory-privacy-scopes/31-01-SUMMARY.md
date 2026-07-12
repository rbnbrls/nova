---
phase: 31-per-person-memory-privacy-scopes
plan: 01
subsystem: nova-core
tags: [memory, privacy, scope, tools, agent, briefing]
requires: [30-02-PLAN.md]
affects:
  - services/nova-core/alembic/versions/0006_add_memory_scope.py
  - services/nova-core/app/tools/memory.py
  - services/nova-core/app/tools/__init__.py
  - services/nova-core/app/db.py
  - services/nova-core/app/agent.py
  - services/nova-core/app/scheduler.py
tech-stack:
  added: []
  patterns:
    - Scoped memory insertion with private/household enum
    - Multi-user retrieval filtering at SQL level for privacy enforcement
    - Briefing functions append per-user memory context
key-files:
  created:
    - services/nova-core/alembic/versions/0006_add_memory_scope.py
    - services/nova-core/app/tools/memory.py
    - services/nova-core/tests/test_memory.py
  modified:
    - services/nova-core/app/tools/__init__.py
    - services/nova-core/app/db.py
    - services/nova-core/app/agent.py
    - services/nova-core/app/scheduler.py
decisions:
  - "Memory scope defaults to 'private' — users must explicitly opt-in to household sharing"
  - "SQL WHERE clause `(user_id = $1 AND scope = 'private') OR scope = 'household'` is the sole privacy enforcement point"
  - "forget tool requires user confirmation via confirmation gate (like destructive calendar/task ops)"
  - "remember tool is additive and does NOT need confirmation"
  - "Shared helper lives in app/db.py to avoid circular imports between scheduler and agent"
metrics:
  duration: 132s
  completed_date: 2026-07-12
  tasks_total: 3
  tasks_completed: 3
status: complete
---

# Phase 31 Plan 01: Per-Person Memory & Privacy Scopes Summary

**One-liner:** Add `scope` column (private/household) to memories table, create `remember`/`forget`/`list_memories` tools with scope support via TDD, and wire memory retrieval with privacy filtering into the agent loop and scheduler briefings.

## Tasks Executed

### Task 1 — DB Migration: add `scope` column to memories table (Commit: `db24e19`)

- Created `alembic/versions/0006_add_memory_scope.py`
- Adds `scope TEXT NOT NULL DEFAULT 'private'` column to `memories` table
- Downgrade drops the column
- Follows exact pattern from `0005_voice_room_defaults.py`
- No CHECK constraint — scope validation is application-level (JSON Schema enum in tool definition)

### Task 2 — Memory tools: remember, forget, list_memories (Commit: `636d9f6` TDD RED, `ec1a692` TDD GREEN)

- **TDD RED:** 12 tests written covering registration, schema validation, required params, invalid scope values — all failing as expected
- **TDD GREEN:** Implemented `app/tools/memory.py` with three tools:
  - `remember(content, scope)` — inserts into `memories` with resolved user_id, scope defaults to `"private"`
  - `forget(content_pattern, scope)` — deletes where user_id matches requester, content ILIKE match, optional scope filter
  - `list_memories(scope)` — returns user's own memories filtered by optional scope
- Registered `memory` module in `tools/__init__.py`

### Task 3 — Memory retrieval + agent/briefing integration (Commit: `119c203`)

- **Part A:** Added `get_user_memories(user_name)` async helper in `app/db.py`
  - SQL: `WHERE (user_id = $1 AND scope = 'private') OR scope = 'household'`
  - Returns formatted bullet list or empty string
- **Part B:** Agent system prompt injection in `run_agent()`
  - Fetches memories via `get_user_memories(user)` before building prompt
  - Appends `"Relevant memories about {user} and the household:\n{memories_context}"` when memories exist
- **Part C:** Added `"remember"` and `"forget"` to `_MAX_MUTATING_TOOLS`; `"forget"` added to confirmation gate; `_summarize_action` extended
- **Part D:** Both `send_morning_briefing_for_user` and `send_weekly_briefing_for_user` include memory context with `"*Nova remembers:*"` header

## Deviations from Plan

None — plan executed exactly as written.

## Threat Surface Scan

All three threat register items (T-31-01, T-31-02, T-31-03, T-31-04) are mitigated as specified:
- T-31-01: Information Disclosure — mitigated by SQL WHERE clause `(user_id = $1 AND scope = 'private') OR scope = 'household'`
- T-31-02: Tampering — mitigated by `DELETE WHERE user_id = $1` in forget tool
- T-31-03: Spoofing — mitigated by `Tool.run()` injecting `user` param from authenticated agent loop, not LLM args
- T-31-04: Elevation of Privilege — mitigated by JSON Schema enum `["private", "household"]`

No new threat surface introduced beyond what the plan's threat model covered.

## Self-Check: PASSED

| Check | Status |
|-------|--------|
| Migration file exists | PASSED |
| `remember` in TOOLS | PASSED |
| `forget` in TOOLS | PASSED |
| `list_memories` in TOOLS | PASSED |
| `get_user_memories` is coroutine | PASSED |
| `remember` in `_MAX_MUTATING_TOOLS` | PASSED |
| `forget` in `_MAX_MUTATING_TOOLS` | PASSED |
| `forget` in confirmation gate | PASSED |
| Morning briefing has memory context | PASSED |
| Weekly briefing has memory context | PASSED |
