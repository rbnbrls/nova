---
phase: 07-evaluation-suite
verified: 2026-07-12T16:00:00Z
status: passed
score: 7/7 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 7: Evaluation Suite Verification Report

**Phase Goal:** A golden-conversation eval suite runs tool-calling scenarios against the real local model (with deterministic mock fallback in CI), gating changes to the system prompt, tool specs, or model.

**Verified:** 2026-07-12T16:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | test_evals.py contains all 11 eval scenarios (7 existing + 4 new) | ✓ VERIFIED | File has 11 `test_eval_*` functions: `test_eval_complete_task_confirmation_scenario`, `test_eval_calendar_query_scenario`, `test_eval_important_emails_scenario`, `test_eval_dutch_date_parsing_scenario`, `test_eval_multi_tool_turn_scenario`, `test_eval_refusal_case_scenario`, `test_eval_calendar_creation_scenario`, `test_eval_task_with_deadline_scenario`, `test_eval_priority_task_scenario`, `test_eval_weather_refusal_scenario`, `test_eval_suite_is_discoverable_by_pytest` |
| 2 | Each scenario runs deterministically under pytest with mocked LLM | ✓ VERIFIED | All 11 pass via `pytest services/nova-core/tests/test_evals.py`. Each uses the `if not await llm.is_ready():` pattern with `unittest.mock.patch` + `AsyncMock` for deterministic mock paths. |
| 3 | Calendar creation scenario tests resolved datetime -> create_event tool call | ✓ VERIFIED | `test_eval_calendar_creation_scenario` (lines 216-247) — mock LLM returns `create_event` with ISO datetime args (`start`, `end`); asserts `[CONFIRMATION_REQUIRED]` in response (confirmation gate intercept). |
| 4 | Task-with-deadline scenario tests due_at parameter -> add_task tool call | ✓ VERIFIED | `test_eval_task_with_deadline_scenario` (lines 254-285) — mock LLM returns `add_task` with `due_at` ISO date; asserts `mock_call.called` and `"buy milk"` in response. |
| 5 | Priority task scenario tests priority=high -> add_task tool call | ✓ VERIFIED | `test_eval_priority_task_scenario` (lines 292-323) — mock LLM returns `add_task` with `priority: "high"`; asserts `mock_call.called` and `"review budget"` in response. |
| 6 | Weather/proactive refusal scenario tests graceful refusal without tool calls | ✓ VERIFIED | `test_eval_weather_refusal_scenario` (lines 330-344) — mock LLM returns content-only dict (no `tool_calls`); asserts `"don't have"`/`"can't"`/`"weather"` in response indicating refusal. |
| 7 | Suite is discoverable by pytest collection | ✓ VERIFIED | `test_eval_suite_is_discoverable_by_pytest` asserts all 11 function names via `dir(sys.modules)` and checks `len >= 11`. pytest collection confirms all 11 tests discovered. |

**Score:** 7/7 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `services/nova-core/tests/test_evals.py` | Contains 11 eval scenarios in evaluation suite | ✓ VERIFIED | 368 lines, 10 async + 1 sync test function. Substantive implementation — no stubs or placeholders. All 11 tests pass with mocked LLM. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| Mock `app.llm.chat` return value (dict) | `run_agent` expected message format | `{role, content, tool_calls}` | ✓ WIRED | All tests monkeypatch `app.llm.chat` via `patch("app.llm.chat", new_callable=AsyncMock)`. Return dicts have correct `role`, `content`, `tool_calls` keys matching what `run_agent` expects. |
| Mock `app.tools.call_tool` return value (string) | `run_agent` tool-result feed | AsyncMock returning string | ✓ WIRED | All tests monkeypatch `app.tools.call_tool` via `patch("app.tools.call_tool", new_callable=AsyncMock)`. Return values are strings compatible with `run_agent`'s tool-result feed. |

### Data-Flow Trace (Level 4)

N/A — test file. No dynamic rendering data to trace.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 11 eval tests pass with mocked LLM | `pytest services/nova-core/tests/test_evals.py -x --tb=short -q` | `11 passed in 0.36s` | ✓ PASS |
| Discoverability test verifies all 11 names | `test_eval_suite_is_discoverable_by_pytest` | Function asserts all 11 names in `dir()` with `>= 11` minimum | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| EVAL-01 | 07-01-PLAN.md | Evaluation scenarios cover tool-calling scenarios | ✓ SATISFIED | 11 scenarios in test_evals.py covering task confirmation, calendar query, email query, Dutch date parsing, multi-tool turns, refusal cases, calendar creation, task deadline, priority task, weather refusal |
| EVAL-02 | 07-01-PLAN.md | Evals run automatically on changes; scored threshold | ✓ SATISFIED (plain pass/fail) | Suite discoverable by pytest; Dockerfile has `RUN pytest` gating all changes. Scored threshold explicitly deferred per CONTEXT.md (D-01). |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `services/nova-core/tests/test_evals.py` | — | None | — | No debt markers (TBD/FIXME/XXX), no placeholder implementations, no stubs, no console.log debugging, no TODO/HACK markers found in the verified file. |

### Gaps Summary

No gaps found. All must-haves are verified, all tests pass, all artifacts are substantive and wired.

---

_Verified: 2026-07-12T16:00:00Z_
_Verifier: the agent (gsd-verifier)_
