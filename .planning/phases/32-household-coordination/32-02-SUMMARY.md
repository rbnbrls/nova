---
phase: 32-household-coordination
plan: 02
subsystem: tools
tags:
  - chores
  - recurrence
  - rotation
  - household
  - alembic
requires:
  - 32-01 (grocery + relay tools)
provides:
  - HC-02: Recurring chores with rotation tracking
affects:
  - services/nova-core/app/tools/__init__.py
  - services/nova-core/alembic/versions/
tech-stack:
  added:
    - chores.py: 3 tools (add_chore, list_chores, complete_chore) — tasks table extension, @tool decorator
    - chore_rotation_log table for append-only completion history
  patterns:
    - Recurrence stored as text (cron-like or human keywords like "weekly", "biweekly", "monthly")
    - Rotation uses flip logic: last_rotation_assignee_id determines next assignee
    - Fair-share computed from chore_rotation_log (last 30 days, same rotation_group)
    - Nudge fires when one user is ahead by 2+ completions
key-files:
  created:
    - services/nova-core/alembic/versions/0010_add_chore_recurrence.py
    - services/nova-core/app/tools/chores.py
    - services/nova-core/tests/test_chores.py
  modified:
    - services/nova-core/app/tools/__init__.py
decisions:
  - Chores reuse tasks table with is_chore=true flag rather than a separate table
  - Rotation is group-scoped: chores in same rotation_group share a rotation pool
  - First completion flips from original assignee; subsequent completions flip from last_rotation_assignee_id
  - Fair-share nudges only appear for chores with a rotation_group set
  - Migration 0010 (0009 was already taken by backfill migration)
metrics:
  duration: ~30 minutes
  completed_date: 2026-07-12
tasks:
  total: 3
  completed: 3
status: complete
---

# Phase 32 Plan 02: Recurring Chores with Rotation

Added recurring chore support with rotation tracking and fair-share nudges. Chores are stored in the existing `tasks` table with `is_chore=true` flag. A new `chore_rotation_log` table tracks completion history for fair-share computation.

## Task Results

### Task 1: Migration 0010 — add chore columns to tasks + chore_rotation_log
- **Status:** ✅ Complete
- **Files:** `alembic/versions/0010_add_chore_recurrence.py`
- **Commit:** `a2a8e15`
- Added 4 columns to `tasks`: `recurrence_pattern` (TEXT), `rotation_group` (TEXT), `last_rotation_assignee_id` (UUID FK→users), `is_chore` (BOOLEAN, default false)
- Created `chore_rotation_log` table: id, chore_id (FK→tasks CASCADE), completed_by (FK→users), rotation_group, completed_at
- Follows 0002_add_task_priority.py pattern for add_column
- Uses 0010 revision (0009 was taken by existing backfill migration)

### Task 2: Create chore tools
- **Status:** ✅ Complete
- **Files:** `app/tools/chores.py`
- **Commit:** `b697b36`
- Three tools:
  - `add_chore` — creates a task with is_chore=true, validates recurrence_pattern is non-empty, supports rotation_group scoping
  - `list_chores` — shows active chores with assignee, recurrence info, rotation group, and fair-share nudge when one user is ahead by 2+ completions in the last 30 days
  - `complete_chore` — marks done, logs to chore_rotation_log, computes next assignee via flip logic, inserts next instance, computes fair-share nudge

### Task 3: Wire into __init__.py + tests
- **Status:** ✅ Complete
- **Files:** `app/tools/__init__.py`, `tests/test_chores.py`
- **Commit:** `5181623`
- `__init__.py` imports `chores` module for tool registration
- 11 tests covering: add_chore (creation, validation, rotation_group), list_chores (format, empty, fair-share nudge, filter), complete_chore (rotation, fairness nudge, non-recurring, not found)

## Deviations from Plan

- **Migration revision 0010 instead of 0009:** The revision `0009` was already taken by a committed backfill migration (`0009_backfill_channel_identities_whatsapp.py`). Used `0010` with `down_revision: "0009"` instead. Alembic head is now 0010.

## Key Decisions

1. **Rotation flip logic:** On first completion, flips from original assignee (initialization). On subsequent completions, flips from `last_rotation_assignee_id` (the person who just completed it). This ensures fair alternation after the first cycle.
2. **Group-scoped fairness:** The `rotation_group` field scopes which chores share a rotation/fairness pool. Chores in different groups have independent rotation tracking.
3. **30-day window for fair-share:** Nudge considers completions in the last 30 days, making it responsive to recent activity rather than cumulative history.
4. **No auto-scheduling:** Due dates are not auto-computed from recurrence patterns — the chore simply re-queues with a new assignee on completion.

## Verification

- ✅ `tool_specs()` includes all 3 chore tools (add_chore, list_chores, complete_chore) + 4 grocery/relay tools
- ✅ 22/22 tests pass across groceries, chores, and tasks test files
- ✅ Alembic head is 0010 (single head)
- ✅ add_chore with blank recurrence_pattern returns error
- ✅ complete_chore on recurring chore creates next instance with swapped assignee
- ✅ list_chores shows fair-share nudge when completions are imbalanced (≥2 difference)
- ✅ complete_chore on non-recurring chore just marks done

## Self-Check: PASSED

All created files exist, all commits found, all tests pass.
