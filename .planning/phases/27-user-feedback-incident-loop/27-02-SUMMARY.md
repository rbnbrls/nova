---
phase: 27-user-feedback-incident-loop
plan: 02
subsystem: nova-core
tags: [feedback, agent-loop, whatsapp]
requires: [27-01]
provides: [feedback integration in agent loop and whatsapp channel]
affects: [agent.py, whatsapp.py]
tech-stack:
  added: []
  patterns: [fire-and-forget file_feedback_issue, fast-path early return in agent loop]
key-files:
  created: []
  modified:
    - services/nova-core/app/agent.py
    - services/nova-core/app/channels/whatsapp.py
decisions:
  - "Feedback fast-path in agent loop returns early before LLM invocation (no LLM cost for feedback)"
  - "Context capture on success and got-stuck paths; NOT on timeout/exception paths"
  - "WhatsApp reaction detection runs before adapter parsing — reactions never reach agent loop"
  - "Fire-and-forget asyncio.create_task for issue filing — never blocks message processing"
  - "Unrecognized (household) senders silently skipped — no issue filed"
metrics:
  duration_minutes: 10
  completed_date: "2026-07-12"
status: complete
---

# Phase 27 Plan 02: Agent Loop & WhatsApp Feedback Wiring Summary

**One-liner:** Wired the feedback module into the agent loop (fast-path text detection + context capture on success/got-stuck) and the WhatsApp channel handler (👎 reaction parsing + issue filing) — 80 tests pass with zero regressions.

---

## Deviations from Plan

None — plan executed exactly as written.

- **Added logging to agent.py:** Agent.py had no logger; added `import logging` and `log = logging.getLogger("nova-core.agent")` to support the `log.info()` call in the feedback fast-path (referenced in plan's code block).

---

## Decisions Made

- **Fast-path before LLM:** Feedback detection executes before history truncation, tool speculation, and `messages.append()`. Feedback messages never waste LLM tokens.
- **Context capture placement:** On the no-tool-calls success path (after tracing emit) and on the got-stuck path (after tracing emit). NOT on timeout or exception paths — those produce no meaningful conversation turn.
- **Reaction handling before adapter:** `_parse_reaction()` runs before `WhatsAppAdapter.process_incoming()` — reactions are never treated as inbound messages.
- **Fire-and-forget:** Both `file_feedback_issue()` calls use `asyncio.create_task()` — the issue filing never blocks the message response.

---

## Test Results

```
80 passed, 1 skipped in 0.43s
```

Test suites verified:
- **test_agent.py** (4 tests) — agent loop still works with feedback fast-path
- **test_feedback.py** (36 tests) — feedback module fully functional
- **test_webhooks.py** (23 tests) — WhatsApp text/image/reaction handling unchanged
- **test_tracer.py** (4 tests) — tracing unchanged
- **test_audit.py** (5 tests, 1 skipped) — audit unchanged
- **test_reliability.py** (8 tests) — reliability unchanged
- **test_whatsapp_otp.py** (8 tests) — OTP unchanged
- **test_security.py** (1 test) — security unchanged

---

## Decision Coverage

| Decision | Code Reference | Verified |
|----------|---------------|----------|
| D-01 (text detection in agent loop) | `agent.py` feedback fast-path, `whatsapp.py` reaction handling | ✅ |
| D-02 (context capture) | `agent.py` success + got-stuck paths → `feedback_context.capture()` | ✅ |
| D-03 (ForgejoClient) | `asyncio.create_task(file_feedback_issue(...))` in both paths | ✅ |
| D-04 (feedback labels) | Called through `file_feedback_issue` which passes `labels=["feedback"]` | ✅ |

---

## Threat Surface

| Threat ID | Category | Component | Severity | Status |
|-----------|----------|-----------|----------|--------|
| T-27-04 | Information Disclosure | `agent.py` context capture | low | Mitigated — `FeedbackContext` is in-memory dict only |
| T-27-05 | Denial of Service | `detect_feedback_text` regex | low | Accepted — fixed patterns, no ReDoS risk |
| T-27-06 | Spoofing | WhatsApp `from` field | low | Accepted — same trust boundary as normal WhatsApp messages |
| T-27-SC | Supply Chain | pip install | high | Mitigated — zero new dependencies |

---

## Self-Check: PASSED

- [x] `agent.py` imports feedback module and adds fast-path for "that was wrong" text
- [x] `agent.py` captures `TurnContext` on normal success and got-stuck exit paths
- [x] `whatsapp.py` parses reaction payloads and files feedback issues for 👎
- [x] All existing tests pass with zero regressions
- [x] Decision coverage: D-01 through D-04 referenced in code annotations
- [x] Channel inheritance: Telegram and API channels automatically get text-based feedback through `run_agent()`
