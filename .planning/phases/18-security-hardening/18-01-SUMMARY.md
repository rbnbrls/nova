---
phase: 18-security-hardening
plan: 01
subsystem: nova-core, ops-bridge
tags: [security, testing, auth, regression]
requires: []
provides: [SEC-01, SEC-02, SEC-03, D-02, D-03]
affects: [services/nova-core, services/ops-bridge]
tech-stack:
  added: []
  patterns:
    - AsyncMock-based call-invariant tests to prove security gates run before business logic
    - Enumeration of all auth failure modes in a single parameterized test pattern
key-files:
  created: []
  modified:
    - services/nova-core/tests/test_security_hardening.py
    - services/ops-bridge/tests/test_bridge.py
decisions:
  - T-18-01: hmac.compare_digest at main.py:144 — ordering test guards against future reordering
  - T-18-02: All auth errors return {"detail": "Unauthorized"} — consistency test proves no leakage
  - T-18-03: ops-bridge app.py:70 already uses hmac.compare_digest — existing test proves it
metrics:
  duration: "5 min"
  completed_date: "2026-07-12"
status: complete
---

# Phase 18 Plan 01: Security Hardening — Auth Ordering & Error Consistency Tests

One wave, two tasks: Add regression-proof tests proving that auth checks gate all user-attribution logic in nova-core, and that ops-bridge rejects missing X-Bridge-Token headers.

## Success Criteria

1. ✅ Auth ordering test proves unauthenticated requests with `user=Ruben` return 401 without calling `run_agent` — SEC-01 satisfied with regression-proof test
2. ✅ Auth success test proves valid token with user=Ruben processed normally and `run_agent` receives `user=Ruben` — SEC-02 satisfied
3. ✅ Error consistency test proves all auth failure modes return identical `{"detail": "Unauthorized"}` — D-03 satisfied (no internal details leaked)
4. ✅ ops-bridge missing-header test proves X-Bridge-Token header absence returns 401 — SEC-03 boundary covered
5. ✅ Existing `test_webhook_auth_constant_time` already verifies hmac.compare_digest usage — D-02 satisfied and proven

## Deviations from Plan

None — plan executed exactly as written.

## Threat Surface Scan

No new threat surface introduced. All files are test-only. The tests themselves act as regression guards against the threat model's trust boundaries (T-18-01, T-18-02, T-18-03).

## Known Stubs

None — both files are complete test coverage additions with no placeholder values.

## Commits

| Task | Description | Hash |
|------|------------|------|
| 1 | test(18-security-hardening): add auth ordering and error consistency tests | 1e01acf |
| 2 | test(18-security-hardening): add missing X-Bridge-Token header test | 1514796 |

## Test Results

### Nova-core (test_security_hardening.py) — 3 passed

```
tests/test_security_hardening.py::test_chat_completions_authentication PASSED
tests/test_security_hardening.py::test_auth_blocks_user_attribution_ordering PASSED
tests/test_security_hardening.py::test_auth_error_response_consistency PASSED
```

### Ops-bridge (test_bridge.py) — 6 passed

```
tests/test_bridge.py::test_fingerprint PASSED
tests/test_bridge.py::test_webhook_auth_failure PASSED
tests/test_bridge.py::test_webhook_auth_constant_time PASSED
tests/test_bridge.py::test_webhook_missing_token PASSED
tests/test_bridge.py::test_webhook_new_issue PASSED
tests/test_bridge.py::test_webhook_dedup_comment PASSED
```

## Key Files

### `services/nova-core/tests/test_security_hardening.py`

- `test_auth_blocks_user_attribution_ordering` — Three cases: (1) no header + user=query → 401, no run_agent call; (2) no header + user=body → 401, no run_agent call; (3) valid token + user=query → 200, run_agent called with `user=Ruben`. Proves auth check at main.py:141-145 gates user resolution at line 168 and room resolution at line 147.
- `test_auth_error_response_consistency` — Missing header, no Bearer prefix, and wrong token all return `{"detail": "Unauthorized"}` with 401. Proves no internal-detail leakage per D-03.

### `services/ops-bridge/tests/test_bridge.py`

- `test_webhook_missing_token` — Empty headers + `X-Bridge-Token` absent returns 401 with `"bad or missing X-Bridge-Token"`. Covers the `not x_bridge_token` guard at app.py:70.

## Decisions Made

- All nova-core auth failure modes produce identical `{"detail": "Unauthorized"}` responses — no attacker-informative differences
- ops-bridge uses `hmac.compare_digest` (constant-time) for token comparison — already verified by existing test
- Ordering test patched `run_agent` with `AsyncMock` to detect whether the agent loop is reached — any future reordering that places user attribution before auth will cause a test failure

## Self-Check: PASSED

- ✅ `services/nova-core/tests/test_security_hardening.py` exists with 3 test functions
- ✅ `services/ops-bridge/tests/test_bridge.py` exists with 6 test functions
- ✅ Commit `1e01acf` exists in git log
- ✅ Commit `1514796` exists in git log
- ✅ All tests pass in both services
