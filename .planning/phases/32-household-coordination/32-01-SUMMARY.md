---
phase: 32-household-coordination
plan: 01
subsystem: tools
tags:
  - groceries
  - relay
  - household
  - alembic
requires:
  - 32-00 (Phase 32 planning)
provides:
  - HC-01: Message relay between household members
  - HC-03: Grocery list separate from tasks
affects:
  - services/nova-core/app/tools/__init__.py
  - services/nova-core/alembic/versions/
tech-stack:
  added:
    - groceries.py: 3 tools (add_grocery_item, list_groceries, mark_purchased) — asyncpg, @tool decorator
    - relay.py: 1 tool (relay_message) — dispatcher.send_to_user integration
  patterns:
    - All tools follow Phase 4 task tool patterns (@tool decorator, get_pool, async)
    - Foreign keys reference users.id for attribution
    - ILIKE for case-insensitive dedup and match fallbacks
    - Migration follows 0004_audit_log_table.py pattern
key-files:
  created:
    - services/nova-core/alembic/versions/0008_create_grocery_items.py
    - services/nova-core/app/tools/groceries.py
    - services/nova-core/app/tools/relay.py
    - services/nova-core/tests/test_groceries_relay.py
  modified:
    - services/nova-core/app/tools/__init__.py
decisions:
  - Grocery items persist after purchase (purchased flag, no DELETE) for history
  - Auto-dedup uses ILIKE on unpurchased items only — purchased items with same title can be re-added
  - Relay messages formatted with "📩 From {sender}:" prefix and sent with proactive=False (no DND gate)
  - No new Python packages needed — pure asyncpg usage
metrics:
  duration: ~25 minutes
  completed_date: 2026-07-12
tasks:
  total: 3
  completed: 3
status: complete
---

# Phase 32 Plan 01: Grocery List Tools + Message Relay

Grocery list tools (add, list, mark purchased) and message relay tool, with Alembic migration 0008 for the grocery_items table. All follow Phase 4 task tool patterns.

## Task Results

### Task 1: Create grocery_items table migration (Alembic 0008)
- **Status:** ✅ Complete
- **Files:** `alembic/versions/0008_create_grocery_items.py`
- **Commit:** `0162cc9`
- Created grocery_items table with id (UUID PK), title, quantity, added_by FK, added_at, purchased (boolean), purchased_at, purchased_by FK. Non-unique index on title. Follows exactly the pattern from 0004_audit_log_table.py.

### Task 2: Create grocery list tools
- **Status:** ✅ Complete
- **Files:** `app/tools/groceries.py`
- **Commit:** `20448ca`
- Three tools:
  - `add_grocery_item` — inserts to grocery_items table with auto-dedup (ILIKE check on unpurchased items), optional quantity
  - `list_groceries` — shows unpurchased items with who added them, formatted numbered list
  - `mark_purchased` — exact match + ILIKE substring fallback, stores purchaser info

### Task 3: relay.py + __init__.py wiring + tests
- **Status:** ✅ Complete
- **Files:** `app/tools/relay.py`, `app/tools/__init__.py`, `tests/test_groceries_relay.py`
- **Commit:** `93a4489`
- `relay_message` tool validates recipient exists in users table, prevents self-relay, sends via dispatcher.send_to_user() with "📩 From {sender}:" prefix and proactive=False
- `__init__.py` updated to import both groceries and relay modules
- 11 tests all passing: grocery CRUD (5), dedup (2), relay (3)

## Deviations from Plan

None — plan executed exactly as written.

## Key Decisions

1. **Grocery dedup is runtime logic, not DB constraint** — Uses ILIKE SELECT before INSERT. Purchased items with the same title can be re-added (dedup only against unpurchased).
2. **Relay uses proactive=False** — Ensures the message is treated as an inbound-triggered reply, bypassing DND gate and 24h template compliance.
3. **Relay sender determined by tool runner context** — The `user` kwarg is injected by `Tool.run()` from authenticated channel identity, not from tool parameters, preventing sender spoofing (T-32-01 mitigation).

## Verification

- ✅ `tool_specs()` includes all 4 new tools (add_grocery_item, list_groceries, mark_purchased, relay_message)
- ✅ 11/11 tests pass
- ✅ Alembic head is 0008 (migration chain intact)
- ✅ Grocery dedup prevents duplicate unpurchased items
- ✅ Relay self-send guard returns error
- ✅ Relay unknown recipient returns error
- ✅ Existing tests still pass

## Self-Check: PASSED

All created files exist, all commits found, all tests pass.
