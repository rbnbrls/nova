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

---

## Proposed Milestone: Household Motion Replacement

**Goal:** Replace Motion's household planning value with a fully local Nova planning stack:
- shared calendar and tasks
- automatic scheduling and replanning
- at-risk detection and "next action" surfacing
- open standards interoperability so the same calendar/contact data is available from Nova, Nextcloud, and Outlook-compatible clients

**Non-goals:**
- No cloud LLMs
- No proprietary SaaS dependency for core planning
- No fork of Nextcloud or Outlook; use standards, sync bridges, or client profiles instead

### Phase 42: planning data model

**Goal:** Add the canonical household planning schema needed for Motion-style scheduling: task duration, scheduling windows, dependencies, blockers, labels/templates, and contact/address-book records for CardDAV interoperability.

**Requirements**: HOUSEHOLD-PLAN-01, HOUSEHOLD-PLAN-02, HOUSEHOLD-PLAN-03
**Depends on:** Phase 41
**Plans:** 1 plan

Plans:

**Wave 1**

- [ ] 42-01-PLAN.md — Migration 0013: planning columns on tasks (task_duration_min, earliest_start, latest_end, hard_deadline, soft_deadline, labels, template_id, planning_state), task_dependencies join table, 5 contact tables (contacts, contact_emails, contact_phones, contact_addresses, contact_sources). New app/contacts.py CRUD module. Pydantic contact models. Task tool planning-field support (add_task, list_tasks, complete_task).

**Acceptance criteria**

- Tasks can represent scheduling intent beyond simple due dates.
- The database can store shared household contacts independently of Nova chat users.
- The schema is migration-backed and safe to apply on an existing household instance.

### Phase 43: deterministic auto-scheduler

**Goal:** Build the first local planner that turns tasks into time blocks using deadlines, durations, priorities, and household availability.

**Requirements**: HOUSEHOLD-PLAN-04, HOUSEHOLD-PLAN-05
**Depends on:** Phase 42
**Plans:** 1 plan

Plans:

**Wave 1**

- [ ] 43-01-PLAN.md — Planner module (`app/planning.py`) with scoring, slot selection, schedule builder, persistence (`planned_blocks` table via migration 0014), `generate_plan` tool, dashboard plan endpoint/stream integration, and tests for determinism, conflict avoidance, and deadline ordering

**Acceptance criteria**

- Nova can generate a time-blocked plan for a user or household.
- The schedule is deterministic for the same inputs.
- The planner avoids double-booking and respects hard conflicts.

### Phase 44: replanning and risk detection

**Goal:** Make the plan adapt when life changes: meetings run long, new events arrive, tasks slip, or the household gets overloaded.

**Requirements**: HOUSEHOLD-PLAN-06, HOUSEHOLD-PLAN-07, HOUSEHOLD-PLAN-08
**Depends on:** Phase 43
**Plans:** 1 plan

Plans:

**Wave 1**

- [ ] 44-01-PLAN.md — Replanning engine and triggers: calendar-change hooks, task-update hooks, overdue-risk scoring, capacity checks, and "next best action" computation; wire the results into scheduler briefings and the dashboard so the household sees at-risk work before it becomes overdue

**Acceptance criteria**

- Nova can flag tasks that are likely to miss their deadline.
- Nova can recompute the schedule after a calendar change.
- The household sees a clear next action, not just a raw list of tasks.

### Phase 45: task intelligence and household coordination

**Goal:** Upgrade tasks from a flat list to a Motion-like work surface with labels, blockers, recurring templates, shared notes, and lightweight collaboration.

**Requirements**: HOUSEHOLD-PLAN-09, HOUSEHOLD-PLAN-10, HOUSEHOLD-PLAN-11
**Depends on:** Phase 44
**Plans:** 1/1 plans complete

Plans:

**Wave 1**

- [ ] 45-01-PLAN.md — Extend task tools/UI for labels, filters, dependencies, recurring templates, notes/comments, and "assign/share with household member" workflows; update `app/tools/tasks.py`, `app/tools/chores.py`, `app/tools/relay.py`, dashboard activity views, and add tests for label filtering, dependency display, and recurring task behavior

**Acceptance criteria**

- Tasks can be organized by label, blocker, and template.
- Recurring tasks and chores remain first-class and visible in planning.
- The household can add context to a task without losing it in chat.

### Phase 46: calendar intelligence and meeting assistance

**Goal:** Upgrade calendar behavior from CRUD to assistance: availability search, meeting placement, free/busy checks, recurring-event edits, and rescheduling around conflicts.

**Requirements**: HOUSEHOLD-PLAN-12, HOUSEHOLD-PLAN-13, HOUSEHOLD-PLAN-14
**Depends on:** Phase 45
**Plans:** 1/1 plans complete

Plans:

**Wave 1**

- [ ] 46-01-PLAN.md — Expand `app/tools/calendar.py`, `app/main.py`, and related scheduler code with free/busy APIs, "find a slot" helpers, smarter recurring-event handling, and reschedule-aware conflict checks; add tests for meeting placement, recurrence editing, and conflict-aware replanning

**Acceptance criteria**

- Nova can suggest or choose a free slot for a new event.
- Calendar changes trigger replanning instead of manual cleanup.
- Recurring events can be handled as a planning input, not just stored rows.

### Phase 47: CalDAV/CardDAV interoperability

**Goal:** Make the household planning data available outside Nova through open standards so the same calendar and contacts can be used in Nextcloud and Outlook-compatible clients.

**Requirements**: HOUSEHOLD-PLAN-15, HOUSEHOLD-PLAN-16, HOUSEHOLD-PLAN-17
**Depends on:** Phase 42
**Plans:** 1/1 plans complete

Plans:

**Wave 1**

- [ ] 47-01-PLAN.md — Standards/interoperability layer: harden the Radicale CalDAV server configuration, add CardDAV exposure for household contacts, document and test client profiles for Nextcloud and Outlook-compatible setups, and add smoke tests or scripted verification for calendar/contact sync access paths

**Acceptance criteria**

- Calendar data is reachable by Nova and at least one non-Nova client.
- Contacts are reachable through CardDAV, not just Nova's internal DB.
- Nextcloud and Outlook-compatible connection instructions are present and verified against the repo's configured endpoints.
- The open-standards endpoint remains separate from Nova's LLM/runtime concerns.

---

## Backlog Notes for the Next Milestone

- The most important Motion-parity gap is still the planner itself, not more chat features.
- CalDAV/CardDAV should be treated as the interoperability contract for the household, with Nova acting as the intelligence layer on top.
- If Outlook needs a bridge rather than native sync for a given household setup, keep that bridge outside Nova Core and document it as a client compatibility concern.
