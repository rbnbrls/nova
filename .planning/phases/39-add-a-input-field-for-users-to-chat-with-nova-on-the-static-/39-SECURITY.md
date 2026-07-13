---
phase: 39
slug: dashboard-chat-box
status: verified
threats_open: 0
asvs_level: 1
created: 2026-07-13
---

# Phase 39 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Browser (client) → Nova API | Untrusted LLM-generated text crosses from backend into DOM via fetch response | LLM reply text (untrusted, may contain XSS payloads) |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-39-01 | Spoofing (XSS) | `updateChat()` in app.js via innerHTML of `data.reply` | high | mitigate | `escapeHtml()` wraps both `userMessage` and `novaReply` before innerHTML assignment. Function exists at app.js:197 and is used at lines 805/811. | closed |
| T-39-02 | Denial of Service | `POST /dashboard/chat` with empty/whitespace messages | low | mitigate | Backend validates `not req.message or not req.message.strip(): raise HTTPException(400)`. | closed |
| T-39-03 | Denial of Service | `POST /dashboard/chat` long-running agent loop blocking FastAPI worker | low | accept | Agent loop protected by `nova_max_turn_timeout` (default 120s). Browser fetch may timeout — frontend shows error gracefully via try/catch. | closed |
| T-39-SC | Tampering | npm/pip/cargo installs | high | mitigate | Zero new packages. Frontend is vanilla HTML/CSS/JS. Backend uses only existing dependencies (FastAPI, pydantic, asyncpg). | closed |

*Status: closed — mitigation confirmed or accepted risk documented.*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| R-39-01 | T-39-03 | Agent loop timeout may cause client-side timeout before backend responds. Graceful error handling shown to user. Acceptable for single-turn dashboard chat where long-running responses are rare. | design | 2026-07-13 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-13 | 4 | 4 | 0 | gsd-secure-phase |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-13
