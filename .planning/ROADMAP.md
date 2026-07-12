# Roadmap: Nova

## Overview

Nova's foundation (infra, CI/CD, local AI runtime, and the Nova Core agent loop with
stubbed tools) is already live — docs/roadmap.md Phases 0-3. This roadmap covers the next
six phases that turn that foundation into a household assistant people actually use daily:
a hardened test/eval harness, real tool backends (tasks/calendar/email), the WhatsApp
channel, the voice channel, proactive pushes, and a read-only LAN dashboard. Per the
project's explicit "Horizontal Layers" build mode, phases are complete technical layers
built in dependency order — test harness and DB driver first as pure enablers, then real
tool backends as the single biggest unlock (critical path for WhatsApp validation quality,
voice usefulness, the scheduler, and the dashboard), then the channels and surfaces that sit
on top of those tools.

**Milestone v1.1 "User Preferences"** (Phases 7-10) builds on that shipped foundation.
It replaces the static `NOVA_WHATSAPP_USERS` env-var mapping with a DB-backed preferences
store, lets Ruben and Méral self-link their own WhatsApp numbers via an OTP-verified
dashboard flow, gives each of them independent control over when their morning and new
weekly briefings arrive, and adds per-user Do Not Disturb windows that gate proactive
pushes without ever touching inbound chat. Phases are sequenced by architectural seam —
schema/identity correctness first (highest regression risk: the household's only WhatsApp
channel), then onboarding, then scheduling shape, then the cross-cutting DND layer last.
**Status: SUPERSEDED by v2.0 — roadmapped but unbuilt, retained for reference.**

**Milestone v2.0 "Reliability & Security Hardening"** (Phases 11-12) is a small, focused
internal-quality milestone against the already-working codebase — not a feature milestone.
It closes the still-open, code-solvable concerns from `.planning/codebase/CONCERNS.md`,
scoped strictly to the Reliability and Security buckets, so Nova fails gracefully and never
trusts an unauthenticated caller. Phase 11 makes the chat path resilient (Ollama retry/backoff,
friendly fallback instead of a raw 500, a whole-turn wall-clock budget, and bounded history
truncation). Phase 12 closes the two auth gaps (chat-API caller authentication before trusting
the `user` field, and a constant-time ops-bridge token compare). Deliberately excluded from
v2.0: robustness polish, infra reproducibility (`:latest` pins), and server-side cross-channel
memory (a feature, not a fix) — these stay in the backlog.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Test Harness & Tool-Call Validation Foundation** - Pytest suite gates the Docker build/Coolify deploy; DB driver wired; malformed tool-call args are rejected, not silently dropped
- [x] **Phase 2: Household Tool Backends & Eval Suite** - Real tasks/calendar/email tool bodies, minimal write confirmation, and a golden-conversation eval suite against the real local model (completed 2026-07-11)
- [x] **Phase 3: WhatsApp Channel** - Dedicated business number, raw-body signature-verified webhook, sender-to-user attribution, graceful fallback for unknown senders (completed 2026-07-11)
- [x] **Phase 4: Voice Channel** - ESPHome satellite(s) + iPhone via HA Assist (Wyoming Whisper/Piper), validated under concurrent GPU load (completed 2026-07-11)
- [x] **Phase 5: Proactive Scheduler** - Morning briefing, task reminders, important-email push, template-aware sends outside the WhatsApp 24h window (completed 2026-07-11)
- [x] **Phase 6: Read-Only Dashboard** - LAN-only dashboard mirrors chat/voice data, auto-refreshes, grouped by assignee with overdue flags (completed 2026-07-11)
- [ ] **Phase 7: Preferences Schema & Identity Migration** - Postgres-backed preferences/identity store replaces the static WhatsApp env-var mapping, with zero-downtime cutover for Ruben & Méral
- [ ] **Phase 8: WhatsApp Self-Service OTP Linking** - Household members link or re-link their own WhatsApp number via a dashboard-driven, OTP-verified flow
- [ ] **Phase 9: Per-User Dynamic Scheduling** - Per-user toggle/time control over morning and new weekly briefings, firing in the household's actual local timezone
- [ ] **Phase 10: Per-User Do Not Disturb** - Per-user DND windows suppress/defer proactive pushes without ever touching inbound chat
- [x] **Phase 11: Reliability Hardening** - Chat path survives transient Ollama failures, slow/looping turns, and long conversations — friendly fallback instead of a raw 500, never an unbounded request
- [x] **Phase 12: Security Hardening** - The chat API verifies callers before trusting user attribution, and ops-bridge checks its token in constant time

## Phase Details

### Phase 1: Test Harness & Tool-Call Validation Foundation

**Goal**: Every subsequent phase is tested from day one, and the agent loop rejects malformed tool-call arguments instead of silently dropping them
**Depends on**: Nothing (continues from docs/roadmap.md Phase 0-3, already shipped)
**Requirements**: TEST-01, TEST-02, TEST-03, TASK-05
**Success Criteria** (what must be TRUE):

  1. A pytest suite covers nova-core (identity mapping, tool registry, agent loop with a mocked LLM, WhatsApp webhook signature verification) and ops-bridge (dedup/fingerprint)
  2. A failing test suite blocks the Docker image build (`RUN pytest` build-stage step) and therefore the Coolify deploy — not just a post-deploy healthcheck
  3. `heal.sh` runs the test suite before committing an automated fix and rejects a heal branch with failing tests
  4. A tool call with malformed or mismatched arguments is rejected with a reported validation error, not silently executed with fields dropped

**Plans**: TBD

### Phase 2: Household Tool Backends & Eval Suite

**Goal**: Nova's task, calendar, and email tools operate on real data with correct defaults, dates, and scoping, and every write action gets a lightweight confirmation
**Depends on**: Phase 1
**Requirements**: TASK-01, TASK-02, TASK-03, TASK-04, CAL-01, CAL-02, CAL-03, EMAIL-01, EMAIL-02, EMAIL-03, EVAL-01, EVAL-02, CONFIRM-01
**Success Criteria** (what must be TRUE):

  1. User can create, list (filterable by assignee or due date), and complete household tasks via natural language, with the correct default assignee and deadlines resolved against a real current-date/time anchor (not raw LLM math)
  2. User can create and query calendar events via natural language, with correct timezone handling and recurring events (RRULE)
  3. Incoming shared-mailbox email is flagged "important" via a conservative hybrid rules+LLM approach, is queryable via chat/voice, and MS Graph access is scoped to only the shared mailbox (not tenant-wide)
  4. Destructive or externally-visible write actions (delete event, send email) require a lightweight, channel-appropriate confirmation step before executing
  5. A golden-conversation eval suite (task creation, date parsing incl. Dutch/English, multi-tool turns, refusals) runs against the real local model and gates changes to the system prompt, tool specs, or model, with a realistic non-100% pass threshold

**Plans**: TBD

### Phase 3: WhatsApp Channel

**Goal**: Ruben and Méral can reach Nova by WhatsApp with correct attribution, validated against real tool answers
**Depends on**: Phase 2
**Requirements**: WA-01, WA-02, WA-03
**Success Criteria** (what must be TRUE):

  1. User can message Nova via WhatsApp and receive a reply attributed to them by phone number
  2. Nova verifies the webhook signature against the raw, unparsed request body before processing (framework auto-JSON-parsing does not break the HMAC check)
  3. Messages from unrecognized WhatsApp senders fall back gracefully to household identity rather than crashing or being silently dropped

**Plans**: TBD

### Phase 4: Voice Channel

**Goal**: Ruben and Méral can talk to Nova through a voice satellite or their iPhone and get a spoken answer, with acceptable latency under real concurrent GPU load
**Depends on**: Phase 2 (real tools); sequenced after Phase 3 (lower-complexity channel to validate first)
**Requirements**: VOICE-01, VOICE-02, VOICE-03
**Success Criteria** (what must be TRUE):

  1. User can ask Nova a question via a voice satellite (ESPHome + Wyoming Whisper/Piper through HA Assist) and receive a spoken answer
  2. User can ask Nova a question via iPhone (HA Companion Assist) and receive a spoken answer
  3. Voice round-trip latency stays acceptable when the chat model and Whisper STT run concurrently on the shared GPU, validated under concurrent load rather than idle coexistence

**Plans**: TBD

### Phase 5: Proactive Scheduler

**Goal**: Nova proactively keeps Ruben and Méral informed without waiting to be asked
**Depends on**: Phase 2 (real tool data); Phase 3 (WhatsApp push channel)
**Requirements**: PROACTIVE-01, PROACTIVE-02, PROACTIVE-03, PROACTIVE-04
**Success Criteria** (what must be TRUE):

  1. Each user receives a morning briefing summarizing tasks due, today's calendar, and flagged-important email
  2. Users receive reminders for upcoming or overdue tasks
  3. Users receive a push notification when a new "important" email arrives
  4. Proactive WhatsApp pushes sent outside the 24-hour customer-service window use a pre-approved message template rather than free text

**Plans**: TBD

### Phase 6: Read-Only Dashboard

**Goal**: A LAN wall display shows the same household plan available via chat and voice, always current, with zero interaction
**Depends on**: Phase 2 (real DB/CalDAV data); no dependency on Phases 3-5
**Requirements**: DASH-01, DASH-02, DASH-03
**Success Criteria** (what must be TRUE):

  1. A LAN-only static dashboard shows the same calendar/task data available via chat and voice
  2. Dashboard auto-refreshes on a polling interval with zero user interaction required
  3. Dashboard groups tasks by assignee and flags overdue items

**Plans**: TBD
**UI hint**: yes

### Phase 7: Preferences Schema & Identity Migration

**Goal**: Nova's WhatsApp identity resolution and all per-user preference data live in Postgres as the single source of truth, with zero disruption to Ruben & Méral's existing WhatsApp access during cutover
**Depends on**: Phase 3 (existing WhatsApp identity code being migrated), Phase 5 (existing scheduler reading the same static mapping)
**Requirements**: ONBOARD-06, ONBOARD-07
**Success Criteria** (what must be TRUE):

  1. Ruben and Méral's existing WhatsApp numbers keep working identically before and after deploy — no interruption to WA-01/WA-02/WA-03 behavior across the cutover
  2. New preference tables exist in Postgres (verified number, DND window, per-job toggles/times, verification codes) and are seed-migrated with Ruben & Méral's current numbers atomically with the schema change — no separate manual migration step
  3. Nova's WhatsApp sender-to-user resolution reads exclusively from the DB-backed store — no remaining code path in `whatsapp.py` or `scheduler.py` reads `NOVA_WHATSAPP_USERS` directly

**Plans**: TBD

### Phase 8: WhatsApp Self-Service OTP Linking

**Goal**: A household member can link, verify, or replace their own WhatsApp number entirely through the dashboard, with no admin or env-var edit required
**Depends on**: Phase 7 (DB-backed identity + verification-codes schema)
**Requirements**: ONBOARD-01, ONBOARD-02, ONBOARD-03, ONBOARD-04, ONBOARD-05
**Success Criteria** (what must be TRUE):

  1. User can start a WhatsApp-linking flow from the dashboard by selecting their household identity (Ruben or Méral)
  2. User enters a WhatsApp number and receives a one-time verification code on that number via a Meta-approved AUTHENTICATION template
  3. User confirms the code on the dashboard and the number is linked only after correct verification; codes are single-use, expire, and are rate-limited against guessing
  4. Attempting to claim a WhatsApp number already linked to another user is rejected, not silently reassigned
  5. A user with an existing linked number can re-link/replace it with a new number through the same flow

**Plans**: TBD
**UI hint**: yes

### Phase 9: Per-User Dynamic Scheduling

**Goal**: Each user controls independently whether and when their morning and weekly briefings arrive, and scheduled jobs fire at the correct local time
**Depends on**: Phase 7 (DB-backed preferences schema); Phase 8 recommended but not required (real linked users make end-to-end testing meaningful)
**Requirements**: PREF-01, PREF-02, PREF-03, PREF-04, PREF-05, PREF-06, PREF-07
**Success Criteria** (what must be TRUE):

  1. User can toggle their morning briefing on/off from the dashboard
  2. User can pick the time of day their morning briefing sends, and it fires at that household-local time (not shifted by a UTC/timezone bug)
  3. A new weekly briefing job summarizes the upcoming week's tasks and calendar, sent at the user's own chosen day-of-week and time
  4. User can independently toggle the weekly briefing on/off, separate from the morning briefing's toggle
  5. Saving a preference change (toggle or time edit) changes the actual next scheduled send in the running process — no service restart required

**Plans**: TBD
**UI hint**: yes

### Phase 10: Per-User Do Not Disturb

**Goal**: Proactive pushes respect each user's own quiet hours without ever affecting the responsiveness of inbound chat
**Depends on**: Phase 7 (DND schema), Phase 9 (all proactive send call sites, including the new weekly briefing, must exist before DND can wrap them)
**Requirements**: DND-01, DND-02, DND-03, DND-04
**Success Criteria** (what must be TRUE):

  1. User can configure a DND window (start time, end time) that correctly suppresses sends across a window crossing midnight (e.g. 22:00-07:00)
  2. Proactive pushes (briefings, task reminders, important-email alerts) are suppressed during the recipient's own DND window
  3. Alerts suppressed by DND (overdue-task reminders, new-important-email notifications) are deferred and delivered once the DND window ends, rather than silently dropped
  4. A user who messages Nova during their own DND window still receives an immediate reply — DND never delays or blocks inbound chat

**Plans**: TBD
**UI hint**: yes

### Phase 11: Reliability Hardening

**Goal**: Nova's chat path survives transient failures, slow or looping turns, and long-running conversations — the household always gets a graceful reply, never a raw 500 or an unbounded request to the model
**Depends on**: Phase 3 (WhatsApp) and Phase 4 (Voice) are the channels that surface these failures to real users; hardens the shipped Nova Core chat path (docs/roadmap.md Phase 3)
**Requirements**: RELI-01, RELI-02, RELI-03, RELI-04
**Success Criteria** (what must be TRUE):

  1. When Ollama returns a transient error, Nova retries with bounded backoff and still completes the turn, instead of failing outright on the first error (`llm.py`)
  2. When an LLM or tool error is unrecoverable, the user receives a friendly fallback reply (e.g. "Nova is having trouble right now") instead of a raw HTTP 500 with a stack trace (`main.py`, `agent.py`)
  3. A single chat turn stops within an overall wall-clock budget across the whole tool-calling loop, not just after the 6-iteration count (`agent.py`)
  4. A long-running channel conversation is truncated to a bounded history window before being sent to the model, so the request payload cannot grow past the context window (`agent.py`)

**Plans**: TBD

### Phase 12: Security Hardening

**Goal**: Nova never trusts an unauthenticated caller — the chat API verifies who is calling before honoring the `user` attribution, and the ops-bridge token check is timing-safe
**Depends on**: Phase 11 (both harden the same Nova Core boundary; sequenced after reliability so error paths added there also apply to rejected-auth requests). Independent of the v1.1 Phases 7-10.
**Requirements**: SEC-01, SEC-02
**Success Criteria** (what must be TRUE):

  1. A request to `POST /v1/chat/completions` without a valid shared-secret / per-channel auth header is rejected before any `user` attribution is trusted, closing trivial household-member spoofing (`main.py`)
  2. A request carrying the correct auth header is processed normally and attributed to the resolved user, so the legitimate WhatsApp/voice/dashboard channels are unaffected (`main.py`)
  3. ops-bridge compares the `X-Bridge-Token` in constant time via `hmac.compare_digest`, so comparison time no longer varies with how many leading characters match (`ops-bridge/app.py`)

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Test Harness & Tool-Call Validation Foundation | 1/1 | Completed | 2026-07-11 |
| 2. Household Tool Backends & Eval Suite | 4/4 | Complete    | 2026-07-11 |
| 3. WhatsApp Channel | 2/2 | Complete    | 2026-07-11 |
| 4. Voice Channel | 1/1 | Complete    | 2026-07-11 |
| 5. Proactive Scheduler | 2/2 | Complete    | 2026-07-11 |
| 6. Read-Only Dashboard | 1/1 | Complete    | 2026-07-11 |
| 7. Preferences Schema & Identity Migration | 1/1 | Complete | 2026-07-12 |
| 8. WhatsApp Self-Service OTP Linking | 1/1 | Complete | 2026-07-12 |
| 9. Per-User Dynamic Scheduling | 1/1 | Complete | 2026-07-12 |
| 10. Per-User Do Not Disturb | 0/TBD | Not started | - |
| 11. Reliability Hardening | 1/1 | Complete | 2026-07-12 |
| 12. Security Hardening | 1/1 | Complete | 2026-07-12 |
