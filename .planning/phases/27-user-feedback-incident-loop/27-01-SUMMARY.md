---
phase: 27-user-feedback-incident-loop
plan: 01
subsystem: nova-core
tags: [feedback, forgejo, tdd]
requires: []
provides: [app/feedback.py, tests/test_feedback.py]
affects: [agent loop, whatsapp channel]
tech-stack:
  added: []
  patterns: [ForgejoClient integration, deep-copy redaction, module-level singleton]
key-files:
  created:
    - services/nova-core/app/feedback.py
    - services/nova-core/tests/test_feedback.py
  modified: []
decisions:
  - "Feedback patterns use regex with word boundaries to prevent substring false-positives"
  - "Phone redaction uses deep-copy to avoid mutating original context"
  - "ForgejoClient instantiated inline with settings from config (no DI)"
  - "All exceptions caught in file_feedback_issue — caller never blocked"
metrics:
  duration_minutes: 8
  completed_date: "2026-07-12"
status: complete
---

# Phase 27 Plan 01: Feedback Module Summary

**One-liner:** Created the core feedback module (`app/feedback.py`) with text/reaction detection, per-user context cache (max 3 turns), E.164 phone redaction, and structured Forgejo issue filing — all tested with 36 passing tests via TDD (RED → GREEN → REFACTOR).

---

## Deviations from Plan

None — plan executed exactly as written.

- **Pattern correction (Rule 1 - Bug fix):** `"that's not right"` regex was missing the expanded form `"that is not right"`. Added `(?:'?s| is)` alternation. Per D-01.
- **Pattern correction (Rule 1 - Bug fix):** Patterns lacked word boundaries (`\b`) causing false-positives on substrings like `"that's incorrectness"`. Added `\b` to all four patterns. Per D-01.

These were auto-fixed during the GREEN phase before commit, so no additional commit needed.

---

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED (tests) | `f507b93` `test(27-01): add failing tests for feedback module` | ✅ |
| GREEN (impl) | `83a727e` `feat(27-01): implement feedback module` | ✅ |
| REFACTOR | Skipped — no changes needed | ✅ |

---

## Test Results

```
36 passed in 0.25s
```

All test classes:
- **TestDetectFeedbackText** (10 tests) — all matching patterns, case-insensitivity, no-match, edge cases
- **TestDetectFeedbackReaction** (5 tests) — 👎 detection, 👍 rejection, None/empty
- **TestFeedbackContext** (4 tests) — capture, max-turns enforcement, unknown user, multi-user isolation
- **TestTurnContext** (1 test) — all 8 dataclass fields
- **TestRedactContext** (7 tests) — phone removal, deep copy, short numbers preserved
- **TestBuildIssueBody** (3 tests) — structure, truncation, multi-turn
- **TestFileFeedbackIssue** (5 tests) — success, unconfigured, API error, labels, unexpected exception
- **TestFeedbackContextSingleton** (1 test) — module-level instance

---

## Decision Coverage

| Decision | Code Reference | Verified |
|----------|---------------|----------|
| D-01 (text + reaction detection) | `_FEEDBACK_PATTERNS`, `_FEEDBACK_REACTIONS` | ✅ |
| D-02 (context capture, max 3 turns) | `FeedbackContext.capture()`, `_MAX_CONTEXT_TURNS` | ✅ |
| D-03 (ForgejoClient integration) | `file_feedback_issue()`, `redact_context()` | ✅ |
| D-04 (feedback label on issues) | `file_feedback_issue()` labels param | ✅ |

---

## Threat Surface

**T-27-01 (Information Disclosure):** Mitigated via `redact_context()` — phone numbers stripped before issue body construction.
**T-27-02 (Spoofing):** Accepted — false-positive match files noisy issue.
**T-27-03 (Tampering):** Mitigated — ForgejoClient uses token auth over HTTPS.
**T-27-SC (Supply Chain):** Mitigated — zero new external dependencies.

---

## Self-Check: PASSED

- [x] `app/feedback.py` exists with all functions/classes per behavior spec
- [x] `tests/test_feedback.py` has 36 tests all passing
- [x] `feedback_context` singleton importable by Plan 02
- [x] RED → GREEN → (optional) REFACTOR commits in git
- [x] Decision coverage: D-01 through D-04 referenced with `# per D-NN` in code
