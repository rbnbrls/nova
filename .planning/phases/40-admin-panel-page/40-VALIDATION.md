---
phase: 40
slug: admin-panel-page
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-13
---

# Phase 40 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (installed in Dockerfile tester stage) |
| **Config file** | `services/nova-core/tests/conftest.py` (path setup + autouse DB mock) |
| **Quick run command** | `cd services/nova-core && python -m pytest tests/test_admin.py -x` |
| **Full suite command** | `cd services/nova-core && python -m pytest tests/ -x` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd services/nova-core && python -m pytest tests/test_admin.py -x`
- **After every plan wave:** Run `cd services/nova-core && python -m pytest tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 40-01-01 | 01 | 1 | D-05 | — | N/A | unit | `python -m pytest tests/test_admin.py::test_admin_redirect -x` | ❌ W0 | ⬜ pending |
| 40-01-02 | 01 | 1 | D-06 | — | N/A | unit | `python -m pytest tests/test_admin.py::test_admin_html_served -x` | ❌ W0 | ⬜ pending |
| 40-01-03 | 01 | 1 | D-07 | T-admin-08 | index.html NOT modified to add /admin link | smoke | `git diff --exit-code services/nova-core/static/index.html && ! grep -q '/admin' services/nova-core/static/index.html` | ❌ W0 | ⬜ pending |
| 40-01-04 | 01 | 1 | D-08 | T-admin-01 | /admin/stream does NOT require auth (no 401) | unit | `python -m pytest tests/test_admin.py::test_admin_stream_no_auth -x` | ❌ W0 | ⬜ pending |
| 40-01-05 | 01 | 1 | D-10 | — | N/A | unit | `python -m pytest tests/test_admin.py::test_admin_stream_content_type -x` | ❌ W0 | ⬜ pending |
| 40-01-06 | 01 | 1 | D-10 | — | N/A | unit | `python -m pytest tests/test_admin.py::test_admin_stream_payload_shape -x` | ❌ W0 | ⬜ pending |
| 40-01-07 | 01 | 1 | D-02 | T-admin-07 | _check_ollama returns {status, detail, host} | unit | `python -m pytest tests/test_admin.py::test_check_ollama -x` | ❌ W0 | ⬜ pending |
| 40-01-08 | 01 | 1 | D-02 | — | _check_postgres returns table count when reachable | unit | `python -m pytest tests/test_admin.py::test_check_postgres -x` | ❌ W0 | ⬜ pending |
| 40-01-09 | 01 | 1 | D-02 | — | _check_imap returns not_configured when host empty | unit | `python -m pytest tests/test_admin.py::test_check_imap_not_configured -x` | ❌ W0 | ⬜ pending |
| 40-01-10 | 01 | 1 | D-02 | T-admin-06 | _collect_admin_status runs 5 checks concurrently; one failing does not abort others | unit | `python -m pytest tests/test_admin.py::test_collect_status_isolation -x` | ❌ W0 | ⬜ pending |
| 40-01-11 | 01 | 1 | D-03 | — | _collect_channel_status returns per-user per-channel linked status | unit | `python -m pytest tests/test_admin.py::test_collect_channel_status -x` | ❌ W0 | ⬜ pending |
| 40-01-12 | 01 | 1 | UI-SPEC | — | admin.html contains #system-status-panel + #channel-status-panel + per-service cell IDs | smoke | `python -m pytest tests/test_admin.py::test_admin_html_structure -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `services/nova-core/tests/test_admin.py` — stubs for D-02, D-03, D-05, D-06, D-07, D-08, D-10, UI-SPEC structure
- [ ] `services/nova-core/tests/test_admin.py` needs shared fixtures (mocked `llm.is_ready`, mocked `db.get_pool`, mocked `_get_calendar`, mocked `_ha_get`, mocked `_get_imap_connection`) — pattern from `tests/test_dashboard.py`
- [ ] Framework install: none — pytest + pytest-asyncio already in Dockerfile tester stage

*Existing infrastructure covers the framework; new test file is the only Wave 0 deliverable.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SSE status updates render in browser with green/red dots | D-10, UI-SPEC | Requires running browser + live services | Open `/admin` in Chromium/Safari, observe status dots updating every 45s |
| No /admin link visible on dashboard | D-07, D-09 | Visual inspection of rendered dashboard | Open `/dashboard`, confirm no admin link in header/footer/body |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
