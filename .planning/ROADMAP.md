# Roadmap: Nova

## Overview

Nova is a private, fully local household assistant that Ruben & Méral can reach by text or voice, keeping a shared plan (tasks, calendar, important email) — reasoning and data never leave the house.

## Completed Milestones

### v1 milestone (37 phases)

✅ **SHIPPED** 2026-07-12 — Full private household assistant with multi-channel support.

See [v1 milestone archive](.planning/milestones/v1-milestone.md) for complete phase list, decisions, and tech debt.

Deferred from this milestone:

- Phase 37 Plan 2 (process_photo tool + confirmation gate)
- Voice-embedding speaker verification
- HA WebSocket for real-time state
- Warranty receipt filing

## Backlog

Phases and features not yet assigned to a milestone.

*(No backlog items yet — next milestone TBD via /gsd-new-milestone)*

### Phase 38: subdomain and email

**Goal:** Replace MS Graph email integration with IMAP-based reading and SMTP-based sending, driven by a single NOVA_DOMAIN env var. Add send_email tool. Use IMAP flags for deduplication instead of the processed_emails database table.
**Requirements**: TBD
**Depends on:** Phase 37
**Plans:** 3/3 plans complete

Plans:
**Wave 1**

- [x] 38-01-PLAN.md — Config fields (nova_domain, imap_*, smtp_*), remove azure_*, add aioimaplib + aiosmtplib

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 38-02-PLAN.md — Core refactor: IMAP fetch, SMTP send, send_email tool, scheduler adaptation
- [x] 38-03-PLAN.md — Alembic migration to drop processed_emails, rewrite email and scheduler tests

### Phase 39: add a input field for users to chat with nova on the /static/index.html page. Put the chat box in a column below the agenda.

**Goal:** Users can chat with Nova directly from the dashboard — send a message and see Nova's reply without switching to WhatsApp or Telegram.
**Requirements**: TBD
**Depends on:** Phase 38
**Plans:** 1/1 plans complete

Plans:

**Wave 1**

- [x] 39-01-PLAN.md — Backend endpoint (POST /dashboard/chat + Pydantic models + tests) + Frontend (HTML section + CSS styles + JS handlers)

### Phase 40: admin panel page

**Goal:** Add a read-only admin status board at `/admin` (serving `/static/admin.html`) that mirrors the dashboard's glass-panel aesthetic and shows system health (Ollama, Postgres, CalDAV, HA, email IMAP) + per-user channel link status (WhatsApp/Telegram for Ruben and Méral), pushed via SSE every 45 seconds. No auth (LAN-only trust), no write actions, no discoverability from the dashboard.
**Requirements**: TBD
**Depends on:** Phase 39
**Plans:** 1/2 plans executed

Plans:

**Wave 1**

- [x] 40-01-PLAN.md — Backend: `/admin` redirect + `/admin/stream` SSE endpoint with concurrent `_check_*` health checks + per-user channel status query (D-01, D-02, D-03, D-04, D-05, D-08, D-10) + TDD test_admin.py

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 40-02-PLAN.md — Frontend: `admin.html` (glass-panel system-status + channel-status cards + Back-to-Dashboard anchor), `admin.js` (EventSource named-event consumer + DOM-diffing renderer + escapeHtml + error banner), `style.css` admin block, frontend structure tests (D-06, D-07, D-09, D-10)

### Phase 41: admin panel model switcher 

Add a new feature, where the admin can visit the admin panel and switch models in ollama. The user must be able to switch between available models like: qwen3:14b and gemma4:12b and see when Ollama is available again. 
Create an additional "model store" where the admin can browse new models to download and delete models not in use anymore.

**Goal:** Admin panel extended with full Ollama model management — runtime model switching with persistent config (survives restart), live SSE-backed availability display, model store for browsing and downloading new models, and deletion of unused models — all wrapping the Ollama lifecycle behind the existing SSE-driven admin UI with a single-column glass-panel layout.

**Requirements**: ADMIN-MODEL-01, ADMIN-MODEL-02, ADMIN-MODEL-03, ADMIN-MODEL-04, ADMIN-MODEL-05, ADMIN-MODEL-06, ADMIN-MODEL-07, ADMIN-MODEL-08, ADMIN-MODEL-09, ADMIN-MODEL-10
**Depends on:** Phase 40
**Plans:** 3 plans

Plans:

**Wave 0**

- [ ] 41-01-PLAN.md — Foundation: DB migration (app_config table), config helpers, admin_models module with Ollama proxy functions (list, pull, delete, load) + background pull state tracking, llm.py runtime model resolution

**Wave 1** *(blocked on Wave 0)*

- [ ] 41-02-PLAN.md — Backend: model management POST/GET endpoints in main.py (switch, pull, delete, list) with input validation + extended _check_ollama() with model status + extended SSE payload with model loading and pull progress

**Wave 2** *(blocked on Wave 1)*

- [ ] 41-03-PLAN.md — Frontend: admin.html single-column layout with model selector in Ollama card + model store card + switch modal overlay + admin.js model switch/pull/delete handlers with SSE model event integration + style.css model management styles
