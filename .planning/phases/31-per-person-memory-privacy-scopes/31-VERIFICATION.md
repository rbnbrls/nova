---
phase: 31-per-person-memory-privacy-scopes
verified: 2026-07-12T14:57:34Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification: false
gaps: []
deferred:
  - truth: "Dashboard memory browser (view/edit/delete)"
    addressed_in: "Phase 31 (Plan 31-02)"
    evidence: "ROADMAP.md SC-05 — 'Dashboard has a memory browser'. Plan 31-01 explicitly defers frontend + API to Plan 31-02 (per PLAN frontmatter and success criteria #5)"
---

# Phase 31: Per-Person Memory & Privacy Scopes — Verification Report

**Phase Goal:** `remember`/`forget` tools support `private-to-me` vs `household` scope; retrieval is filtered to requester + household scope.

**Verified:** 2026-07-12T14:57:34Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can save a private memory — only they see it in agent context | ✓ VERIFIED | `remember` tool (memory.py:31) accepts `scope` param defaulting to `"private"`. `get_user_memories()` in db.py:37-42 uses SQL `(user_id = $1 AND scope = 'private') OR scope = 'household'` — enforces per-user private filtering. Agent loop (agent.py:108-110) injects memories via `get_user_memories(user)`. Scheduler briefings (scheduler.py:79-82, 150-153) per-user. |
| 2 | User can save a household memory — both users see it in agent context | ✓ VERIFIED | `remember` tool accepts `scope="household"`. SQL `scope = 'household'` returns rows for ALL users (no user_id filter). Both agent loop and scheduler use the same shared query. |
| 3 | User can forget a memory they own (filtered by scope) | ✓ VERIFIED | `forget` tool (memory.py:67-90) uses `DELETE FROM memories WHERE user_id = $1 AND content ILIKE $2` — ownership enforced by `user_id` clause (T-31-02 mitigation). Optional `AND scope = $3` filter. Confirmation gate (agent.py:149) intercepts `forget` before execution. |
| 4 | Ruben's private memories never appear in Méral's conversations or briefing | ✓ VERIFIED | SQL `(user_id = $1 AND scope = 'private')` — when Méral queries, `$1` resolves to Méral's UUID. Ruben's private memories (user_id = Ruben's UUID) are excluded by the WHERE clause. This is THE single enforcement point per D-04. No code path bypasses it. |
| 5 | Household-scope memories appear in both users' agent context | ✓ VERIFIED | SQL `scope = 'household'` has no user_id restriction — every user sees every household memory. Verified in both agent.py:108 and scheduler.py:79/150 paths. |

**Score:** 5/5 truths verified

### Deferred Items

Items not yet met but explicitly addressed in Plan 31-02 (not part of current plan scope).

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | Dashboard memory browser (view/edit/delete) | Plan 31-02 | ROADMAP.md SC-05: "Dashboard has a memory browser". Plan 31-01 explicitly defers per PLAN frontmatter and success criteria. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `services/nova-core/alembic/versions/0006_add_memory_scope.py` | Migration adding `scope` column | ✓ VERIFIED | Creates `scope TEXT NOT NULL DEFAULT 'private'` on `memories` table. Upgrade adds column, downgrade drops it. Revision chain: 0005 → 0006. |
| `services/nova-core/app/tools/memory.py` | `remember`, `forget`, `list_memories` tools | ✓ VERIFIED | 134 lines. Three tools with correct schemas, scope enum validation, ownership enforcement. |
| `services/nova-core/app/tools/__init__.py` | Register `.memory` module | ✓ VERIFIED | Line 10: `from . import tasks, calendar, email, home_assistant, memory`. |
| `services/nova-core/app/db.py` | `get_user_memories()` helper | ✓ VERIFIED | Lines 29-47. Async coroutine, queries `memories` with privacy filter `(user_id = $1 AND scope = 'private') OR scope = 'household'`. Imported and used by both agent.py and scheduler.py. |
| `services/nova-core/app/agent.py` | Memory injection in system prompt + `_MAX_MUTATING_TOOLS` | ✓ VERIFIED | Line 108: `memories_context = await get_user_memories(user)` before prompt build. Lines 109-110: conditional append to system content. Line 21: `_MAX_MUTATING_TOOLS` includes `remember` and `forget`. Line 149: `forget` in confirmation gate. |
| `services/nova-core/app/scheduler.py` | Memory context in briefings | ✓ VERIFIED | Lines 78-82 (morning briefing) and 149-153 (weekly briefing): `get_user_memories(user_name)` with `*Nova remembers:*` header. |
| `services/nova-core/tests/test_memory.py` | Tests for memory tools | ✓ VERIFIED | 12 test cases across 3 test classes covering tool registration, schema validation, required params, invalid scope values. All pass. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| Agent loop `run_agent()` | `get_user_memories()` in db.py | `from .db import get_user_memories` at agent.py:18, called at agent.py:108 | WIRED | Memories injected into system prompt before message list assembly |
| Scheduler `send_morning_briefing_for_user` | `get_user_memories()` in db.py | `from .db import get_user_memories` at scheduler.py:8, called at scheduler.py:79 | WIRED | Memory context appended before dispatch |
| Scheduler `send_weekly_briefing_for_user` | `get_user_memories()` in db.py | Called at scheduler.py:150 | WIRED | Weekly briefing includes memory context |
| `forget` tool | Ownership filter | `DELETE FROM memories WHERE user_id = $1` at memory.py:75/82 | WIRED | Users cannot delete memories they don't own |
| `forget` action | Confirmation gate | `fn_name in ("create_event", "complete_task", "ha_call_service", "forget")` at agent.py:149 | WIRED | Destructive forget requires user confirmation |
| `remember` / `forget` | Audit trail | `_summarize_action` at agent.py:76-82, `record_tool_call` at agent.py:197-204 | WIRED | Both tools recorded in audit trail via `_MAX_MUTATING_TOOLS` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|-------------|--------|-------------------|--------|
| `get_user_memories()` | `rows` | `SELECT ... FROM memories WHERE (user_id=$1 AND scope='private') OR scope='household'` | ✓ Real DB query (asyncpg fetch) | ✓ FLOWING |
| `remember` tool | INSERT args | User-provided `content` + `scope`, `user_id` from DB lookup | ✓ Real DB insert with parameterized query | ✓ FLOWING |
| `forget` tool | DELETE rows | `user_id` + `content_pattern` + optional `scope` | ✓ Real DB delete with ownership filter | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 3 tools registered | `python -c "from app.tools import TOOLS; ..."` | All 3 tools registered, scope enum correct | ✓ PASS |
| `get_user_memories` is coroutine | `python -c "from app.db import get_user_memories; inspect.iscoroutinefunction(...)"` | Confirmed coroutine | ✓ PASS |
| `_MAX_MUTATING_TOOLS` includes remember/forget | `python -c "from app.agent import _MAX_MUTATING_TOOLS; ..."` | Both present in mutating tools set | ✓ PASS |
| 12 test cases pass | `pytest test_memory.py -v` | 12/12 passed (0.24s) | ✓ PASS |

### Requirements Coverage

Plan 31-01 declares `requirements: [MEM-01, MEM-02, MEM-03, MEM-04]`. No separate REQUIREMENTS.md exists; the requirements are captured by ROADMAP.md success criteria SC-01 through SC-04, all of which are satisfied by the implementation.

| Success Criterion | Description | Status | Evidence |
|-------------------|-------------|--------|----------|
| SC-01 | `remember` tool accepts `scope` param (private/household), defaults private | ✓ SATISFIED | memory.py:21-28 schema, memory.py:31 `scope: str = "private"` |
| SC-02 | `forget` filters by scope and only forgets what requester owns | ✓ SATISFIED | memory.py:73-85 `DELETE WHERE user_id=$1`, optional scope filter |
| SC-03 | Memory retrieval filters to requester + household | ✓ SATISFIED | db.py:37-42 SQL WHERE clause |
| SC-04 | Private memories never appear in other user's answers/briefing | ✓ SATISFIED | db.py:39 `(user_id = $1 AND scope = 'private')` — enforced at SQL level |
| SC-05 | Dashboard memory browser | ⏳ DEFERRED | Explicitly deferred to Plan 31-02 per ROADMAP.md and PLAN frontmatter |

### Anti-Patterns Found

None. All files are substantive implementations — no placeholder components, empty handlers, stub API routes, TBD/FIXME/XXX markers, or static-return-only patterns found.

### Human Verification Required

None. All must-haves are verifiable through static code analysis and passing test suite.

## Gaps Summary

**No gaps found.** Plan 31-01 delivers the complete backend scope for Phase 31:

- ✅ Migration adds `scope` column to `memories` table
- ✅ `remember`/`forget`/`list_memories` tools with scope support
- ✅ `get_user_memories()` shared helper with privacy-enforcing SQL
- ✅ Agent loop injects user-scoped memories into system prompt
- ✅ Scheduler briefings include per-user memory context
- ✅ `forget` in confirmation gate, `remember`/`forget` in mutating tools and audit trail

The dashboard memory browser (SC-05) is intentionally deferred to Plan 31-02 as documented in ROADMAP.md and the PLAN frontmatter — not a gap for this plan.

---

*Verified: 2026-07-12T14:57:34Z*
*Verifier: gsd-verifier*
