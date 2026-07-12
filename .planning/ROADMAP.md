# Roadmap: Nova

## Overview

Nova is a private, fully local household assistant that Ruben & Méral can reach by text or voice, keeping a shared plan (tasks, calendar, important email) — reasoning and data never leave the house.

This roadmap is organized by build order: each phase depends on the phases before it. Lower tiers are foundational enablers; higher tiers add user-facing features and polish.

### Build Tiers

| Tier | Theme | Phases |
|------|-------|--------|
| 0 | Foundation | P1-P3 |
| 1 | Tool Backends | P4-P8 |
| 2 | Channels | P9-P10 |
| 3 | Proactive & UX | P11-P12 |
| 4 | User Management | P13-P16 |
| 5 | Reliability & Security | P17-P18 |
| 6 | Multi-Channel Infrastructure | P19-P22 |
| 7 | Multi-Channel UX | P23-P25 |
| 8 | Observability | P26-P29 |
| 9 | Advanced Features | P30-P37 |

## Phases

### Tier 0 — Foundation

### Phase 1: CI/CD & Test Infrastructure

**Goal**: Every subsequent phase is tested from day one. A failing test suite blocks deploy. Automated fix branches are gated by tests.

**Depends on**: Nothing

**Requirements**: TEST-01, TEST-02, TEST-03

**Success Criteria:**

1. A pytest suite covers nova-core (identity mapping, tool registry, agent loop with a mocked LLM, WhatsApp webhook signature verification) and ops-bridge (dedup/fingerprint)
2. A failing test suite blocks the Docker image build (`RUN pytest` build-stage step) and therefore the Coolify deploy
3. `heal.sh` runs the test suite before committing an automated fix on the heal branch, rejects failing branches with exit 3

**Plans**: TBD

---

### Phase 2: Core Agent Loop & Tool Validation

**Goal**: The agent loop runs with tool registration/execution, and malformed tool-call arguments are rejected with a validation error instead of silently dropped.

**Depends on**: Phase 1

**Requirements**: TASK-05

**Success Criteria:**

1. `Tool.run()` validates arguments against JSON Schema and rejects unknown keys not in `properties`
2. Validation errors are surfaced to the LLM as `validation error: ...` strings, not crashes or silent drops
3. Agent loop supports tool-call round trips (LLM requests tool → Nova executes → result fed back to LLM)
4. User attribution via `user` query parameter on `/v1/chat/completions` with a default of "household"

**Plans**: 1 plan

Plans:

- [x] 02-01-PLAN.md — Configurable iteration budget, auto-retry ONCE on tool errors, verification tests

---

### Phase 3: Database Connection & Schema Foundation

**Goal**: Nova has a persistent Postgres connection pool and the core schema for tasks, identity, and preferences.

**Depends on**: Phase 2

**Requirements**: DB-01

**Success Criteria:**

1. `app/db.py` manages an asyncpg connection pool via `get_pool()`/`close_pool()`, wired into FastAPI lifespan
2. Core tables exist: `tasks`, `user_preferences`, `channel_identities`, `channel_verification_codes`, `queued_notifications`, `processed_telegram_updates`
3. All migrations are additive-only — no destructive changes to existing data

**Plans**: 1 plan

Plans:

- [x] 03-01-PLAN.md — Alembic setup, initial migration from 01_schema.sql, db.py refactor to use Alembic, archive old SQL

---

### Tier 1 — Tool Backends

### Phase 4: Task Management

**Goal**: Users can create, list (filterable), and complete household tasks via natural language through the agent loop.

**Depends on**: Phase 3 (DB pool + tasks table)

**Requirements**: TASK-01, TASK-02, TASK-03, TASK-04

**Success Criteria:**

1. `add_task(description, assignee, due_date)` inserts into Postgres `tasks`; `assignee` defaults to the requesting user
2. `list_tasks(assignee, due_before)` filters results; returns all tasks when no filter is specified
3. `complete_task(title)` does an exact-match update falling back to `ILIKE` substring match
4. Agent loop injects `datetime.now(tz).isoformat()` into the system prompt so the LLM resolves relative dates ("tomorrow", "next Friday") against a real anchor

**Plans**: TBD

---

### Phase 5: Calendar Integration

**Goal**: Users can create and query calendar events via natural language through a self-hosted CalDAV server.

**Depends on**: Phase 4 (agent loop + tool pattern)

**Requirements**: CAL-01, CAL-02, CAL-03

**Success Criteria:**

1. `create_event(summary, start, end, description, location)` builds a `VEVENT` and saves via Radicle CalDAV
2. `list_events(start, end)` queries with `expand=True` for recurring event expansion
3. Timestamps with explicit UTC offsets are parsed correctly; naive timestamps normalized to household timezone
4. Radicle service added to `docker-compose.yml`

**Plans**: 1 plan

Plans:

- [x] 05-01-PLAN.md — Add timezone normalization, description param, and RRULE support to create_event/list_events

---

### Phase 6: Email Integration

**Goal**: Nova fetches emails from the shared household mailbox, flags important ones via a conservative hybrid approach, and makes them queryable.

**Depends on**: Phase 4 (agent loop + tool pattern)

**Requirements**: EMAIL-01, EMAIL-02, EMAIL-03

**Success Criteria:**

1. `list_recent_emails(unread_only, max_results)` fetches via MS Graph client-credentials auth, scoped to single mailbox via URL path
2. `classify_importance()` uses keyword rules (bilingual NL/EN) first, then LLM fallback; defaults to `True` (important) on error
3. MS Graph calls hit `/users/{mailbox_email}/messages` — not `/me` or tenant-wide search
4. Mock-data fallback when Azure credentials are not configured

**Plans**: TBD

---

### Phase 7: Evaluation Suite

**Goal**: A golden-conversation eval suite runs tool-calling scenarios against the real local model (with deterministic mock fallback in CI), gating changes to the system prompt, tool specs, or model.

**Depends on**: Phase 4 (tasks), Phase 5 (calendar), Phase 6 (email)

**Requirements**: EVAL-01, EVAL-02

**Success Criteria:**

1. Eval scenarios cover: task completion requiring confirmation, calendar date-range query, important-email query, Dutch-language date parsing, multi-tool turns, and refusal cases
2. Suite runs against real model when `llm.is_ready()`; falls back to deterministic mock otherwise
3. Suite is discoverable by `pytest` and runs automatically as part of the standard test suite
4. Scenarios are behavioral (test what the agent does, not which functions it calls)

**Plans**: 1 plan

Plans:

- [x] 07-01-PLAN.md — Add 4 new eval scenarios (calendar creation, task deadline, priority task, weather refusal) to test_evals.py following established mock pattern

---

### Phase 8: Write Confirmation Gate

**Goal**: Destructive or externally-visible write actions require a lightweight, channel-appropriate confirmation step before executing.

**Depends on**: Phase 4 (tasks — `complete_task`), Phase 5 (calendar — `create_event`)

**Requirements**: CONFIRM-01

**Success Criteria:**

1. Agent loop intercepts `create_event`, `complete_task` before execution (extensible — new write tools registered here as they are added)
2. First request returns `[CONFIRMATION_REQUIRED]` prompt instead of calling the tool
3. Subsequent turn with affirmative response (yes, confirm, ok, ja, sure, approve, go ahead) proceeds with execution
4. Non-affirmative or unrecognized responses do not execute the tool

**Plans**: TBD

---

### Tier 2 — Channels

### Phase 9: WhatsApp Channel

**Goal**: Users can message Nova via WhatsApp with correct sender attribution, signature-verified webhook, and graceful fallback for unknown senders.

**Depends on**: Phase 2 (agent loop), Phase 1 (test harness for regression safety)

**Requirements**: WA-01, WA-02, WA-03

**Success Criteria:**

1. User can message Nova via WhatsApp and receive a reply attributed to them by phone number
2. Nova verifies WhatsApp webhook signatures against the raw, unparsed request body before processing
3. Messages from unrecognized WhatsApp senders fall back gracefully to household identity
4. WhatsApp signature verification uses HMAC-SHA256 + `hmac.compare_digest` for constant-time comparison

**Plans**: 1 plan

Plans:

- [x] 09-01-PLAN.md — Webhook endpoint tests, identity resolution edge cases, outbound message coverage

---

### Phase 10: Voice Channel

**Goal**: Users can talk to Nova through a voice satellite or their iPhone and receive a spoken answer, with acceptable latency under real concurrent GPU load.

**Depends on**: Phase 2 (agent loop), Phase 9 (WhatsApp validates the channel pattern first)

**Requirements**: VOICE-01, VOICE-02, VOICE-03

**Success Criteria:**

1. User can ask Nova a question via a voice satellite (ESPHome + Wyoming Whisper/Piper through HA Assist)
2. User can ask Nova a question via iPhone (HA Companion Assist)
3. Voice round-trip latency is acceptable when the chat model and Whisper STT run concurrently on the shared GPU
4. Concurrent load validation: tested under real load, not idle coexistence

**Plans**: 1 plan

Plans:

- [x] 10-01-PLAN.md — Voice channel test coverage: HA proxy endpoint tests + error handling for LLM/HA unavailability

---

### Tier 3 — Proactive & UX

### Phase 11: Proactive Scheduler

**Goal**: Nova proactively keeps users informed with morning briefings, task reminders, and important-email notifications.

**Depends on**: Phase 4 (tasks), Phase 5 (calendar), Phase 6 (email), Phase 9 (WhatsApp push channel)

**Requirements**: PROACTIVE-01, PROACTIVE-02, PROACTIVE-03, PROACTIVE-04

**Success Criteria:**

1. Each user receives a morning briefing summarizing tasks due, today's calendar, and flagged-important email
2. Users receive reminders for upcoming or overdue tasks
3. Users receive a push notification when a new "important" email arrives
4. Proactive WhatsApp pushes sent outside the 24-hour customer-service window use a pre-approved message template

**Plans**: TBD

---

### Phase 12: Read-Only Dashboard

**Goal**: A LAN-only static dashboard shows the same household plan data available via chat and voice, always current, with zero interaction.

**Depends on**: Phase 4 (tasks), Phase 5 (calendar)

**Requirements**: DASH-01, DASH-02, DASH-03

**Success Criteria:**

1. A LAN-only static dashboard shows calendar/task data available via chat and voice
2. Dashboard auto-refreshes on a polling interval with zero user interaction required
3. Dashboard groups tasks by assignee and flags overdue items

**Plans**: TBD
**UI hint**: yes

---

### Tier 4 — User Management

### Phase 13: DB Preferences & Identity Migration

**Goal**: WhatsApp identity resolution and all per-user preference data live in Postgres as the single source of truth, with zero disruption during cutover.

**Depends on**: Phase 9 (WhatsApp identity code being migrated), Phase 11 (scheduler reading static mapping)

**Requirements**: ONBOARD-06, ONBOARD-07

**Success Criteria:**

1. Ruben and Méral's existing WhatsApp numbers keep working identically before and after deploy
2. Preference tables exist in Postgres (verified number, DND window, job toggles/times, verification codes)
3. WhatsApp sender-to-user resolution reads exclusively from DB — no remaining code path reads `NOVA_WHATSAPP_USERS`
4. Seed-migration populates Ruben & Méral's current numbers atomically with the schema change

**Plans**: TBD

---

### Phase 14: WhatsApp OTP Self-Service Linking

**Goal**: Household members can link, verify, or replace their own WhatsApp number entirely through the dashboard, with no admin or env-var edit required.

**Depends on**: Phase 13 (DB-backed identity + verification-codes schema)

**Requirements**: ONBOARD-01, ONBOARD-02, ONBOARD-03, ONBOARD-04, ONBOARD-05

**Success Criteria:**

1. User starts WhatsApp-linking from the dashboard by selecting their household identity
2. User enters a WhatsApp number and receives a one-time verification code via Meta-approved AUTHENTICATION template
3. Codes are single-use, time-limited, rate-limited; incorrect guesses rejected
4. Claiming a number already linked to another user is rejected, not silently reassigned
5. Existing linked user can re-link/replace through the same flow

**Plans**: 1 plan

Plans:

- [x] 14-01-PLAN.md — WhatsApp OTP self-service linking (AUTHENTICATION template, API endpoints, dashboard modal)

**UI hint**: yes

---

### Phase 15: Per-User Dynamic Scheduling

**Goal**: Each user independently controls whether and when their morning and weekly briefings arrive; scheduled jobs fire at the correct local time.

**Depends on**: Phase 13 (DB-backed preferences), Phase 14 (recommended — linked users make E2E testing meaningful)

**Requirements**: PREF-01, PREF-02, PREF-03, PREF-04, PREF-05, PREF-06, PREF-07

**Success Criteria:**

1. User toggles morning briefing on/off from the dashboard
2. User picks the time of day; briefing fires at that household-local time
3. A new weekly briefing summarizes the upcoming week — per-user toggle independent of morning briefing
4. Preference changes take effect on the next scheduled send — no service restart required

**Plans**: TBD
**UI hint**: yes

---

### Phase 16: Per-User Do Not Disturb

**Goal**: Proactive pushes respect each user's own quiet hours without ever affecting inbound chat responsiveness.

**Depends on**: Phase 13 (DND schema), Phase 15 (all proactive send call sites exist before DND wraps them)

**Requirements**: DND-01, DND-02, DND-03, DND-04

**Success Criteria:**

1. User configures a DND window (start/end) that correctly handles windows crossing midnight
2. Proactive pushes are suppressed during the recipient's own DND window
3. Suppressed alerts are deferred and delivered once the DND window ends — not silently dropped
4. Inbound chat during DND is always answered immediately — never delayed or blocked

**Plans**: TBD
**UI hint**: yes

---

### Tier 5 — Reliability & Security

### Phase 17: Reliability Hardening

**Goal**: The chat path survives transient failures, slow/looping turns, and long conversations — users always get a graceful reply, never a raw 500 or unbounded request.

**Depends on**: Phase 9 (WhatsApp), Phase 10 (Voice) — channels that surface failures

**Requirements**: RELI-01, RELI-02, RELI-03, RELI-04

**Success Criteria:**

1. Transient Ollama errors trigger bounded retry/backoff — turn still completes
2. Unrecoverable errors return a friendly fallback reply — not a raw HTTP 500
3. Single turn has an overall wall-clock budget — not just iteration count
4. Long conversations are truncated to a bounded history window before being sent to the model

**Plans**: TBD

---

### Phase 18: Security Hardening

**Goal**: Nova never trusts an unauthenticated caller — the chat API verifies callers before honoring user attribution; ops-bridge token check is timing-safe.

**Depends on**: Phase 17 (error paths added by reliability apply to rejected-auth requests too)

**Requirements**: SEC-01, SEC-02

**Success Criteria:**

1. `POST /v1/chat/completions` without a valid auth header is rejected before any `user` attribution is trusted
2. A request with a valid auth header is processed normally — legitimate channels unaffected
3. ops-bridge compares `X-Bridge-Token` via `hmac.compare_digest` — constant time, not variable-length comparison

**Plans**: TBD

---

### Tier 6 — Multi-Channel Infrastructure

### Phase 19: Channel Adapter Pattern & Multi-Channel Schema

**Goal**: Database schema supports multi-channel preferences and identities; WhatsApp adapter conforms to a shared `ChannelAdapter` interface.

**Depends on**: Phase 18 (completed security hardening)

**Requirements**: CHAN-01, CHAN-02

**Success Criteria:**

1. `user_preferences` has `last_active_channel TEXT DEFAULT 'whatsapp'` and `channels_enabled TEXT[] DEFAULT '{whatsapp}'` — additive-only
2. `channel_identities` table exists with `UNIQUE(channel, channel_id)` constraint
3. `channel_verification_codes` table generalizes the previous WhatsApp-specific table
4. `queued_notifications` has `channel` column; `whatsapp_number` is nullable
5. WhatsApp adapter conforms to `ChannelAdapter` interface; existing WhatsApp tests pass unchanged
6. `channels/` package exists with `ChannelAdapter` ABC, `InboundMessage`, `dispatcher.py` skeleton, `webhook_router.py` skeleton

**Plans**: TBD

---

### Phase 20: Telegram Bot Foundation

**Goal**: Users can chat with Nova via Telegram with full agent-loop parity — webhook security, formatting, and command menu included.

**Depends on**: Phase 19 (channel adapter skeleton, webhook router)

**Requirements**: TGBOT-01, TGBOT-02, TGBOT-03, TGBOT-04, CMD-01, CMD-02, TGFORMAT-01, TGFORMAT-02, PUSH-03

**Success Criteria:**

1. User can message Nova via Telegram and receive a reply (full agent-loop parity with WhatsApp)
2. Telegram webhook verifies `X-Telegram-Bot-Api-Secret-Token` with constant-time comparison
3. `processed_telegram_updates` dedup table prevents duplicate agent executions on webhook retries
4. Bot registers `/help`, `/tasks`, `/settings` command menu; `/help` returns capabilities summary
5. Outbound messages use HTML parse mode; messages >4096 chars chunked at paragraph boundaries
6. `NOVA_TELEGRAM_ENABLED` feature flag (default OFF) gates all Telegram behavior

**Plans**: TBD

---

### Phase 21: Multi-Channel Identity & Last-Active Tracking

**Goal**: Both inbound channels update last-active tracking atomically; identity resolution works across all channels via `channel_identities`.

**Depends on**: Phase 20 (Telegram bot exists, both channels active)

**Requirements**: CHAN-03

**Success Criteria:**

1. Both WhatsApp and Telegram inbound handlers update `last_active_channel` atomically on every user message
2. `channels/identity.py` resolves `(channel, channel_id)` → user_name using `channel_identities`
3. Existing WhatsApp identity resolution continues to work through the multi-channel resolver — no regression
4. Telegram's BIGINT `chat_id` stored losslessly as TEXT in `channel_identities.channel_id`

**Plans**: TBD

---

### Phase 22: Push Gateway Refactor

**Goal**: All outbound proactive pushes route to the user's last-active channel through a dispatcher, not hardcoded to WhatsApp.

**Depends on**: Phase 21 (identity resolution + last-active tracking)

**Requirements**: PUSH-01, PUSH-02

**Success Criteria:**

1. All 5 scheduler call sites refactored from hardcoded `send_whatsapp_message()` to `dispatcher.send_to_user()`
2. DND-deferred messages queue via the dispatcher pattern and deliver to correct channel when DND ends
3. WhatsApp fallback: if Telegram is last-active but no Telegram identity exists, falls back to WhatsApp
4. All existing WhatsApp tests pass after refactor

**Plans**: TBD

---

### Tier 7 — Multi-Channel UX

### Phase 23: Telegram OTP Self-Service Linking

**Goal**: Users link their Telegram account through the dashboard with OTP verification delivered via Telegram.

**Depends on**: Phase 20 (working Telegram bot), Phase 19 (channel_verification_codes table)

**Requirements**: TGOTP-01, TGOTP-02, TGOTP-03, TGOTP-04

**Success Criteria:**

1. User initiates Telegram linking from the dashboard by selecting their household identity
2. Dashboard sends verification code as a Telegram message; user confirms on dashboard
3. Codes are single-use, time-limited, rate-limited; already-linked chat_ids rejected
4. Existing linked user can re-link/replace with a new chat_id through the same flow
5. Flow writes to `channel_identities` and updates `channels_enabled` to include 'telegram'

**Plans**: TBD
**UI hint**: yes

---

### Phase 24: Telegram DND Queuing (Gap Fix)

**Goal**: DND-deferred alerts destined for Telegram deliver correctly when the DND window ends.

**Depends on**: Phase 22 (dispatcher pattern), Phase 16 (DND logic), Phase 20 (Telegram channel)

**Requirements**: PUSH-02 (gap)

**Success Criteria:**

1. DND-deferred messages queued for Telegram users deliver to Telegram when DND ends
2. Dispatcher correctly routes deferred notifications through the Telegram adapter
3. WhatsApp-only users are unaffected by Telegram-specific DND changes

**Plans**: TBD

---

### Phase 25: Direct Telegram OTP Routing (Gap Fix)

**Goal**: Telegram OTP verification codes route correctly through the Telegram channel without falling back to WhatsApp.

**Depends on**: Phase 23 (OTP flow)

**Requirements**: TGOTP-02 (gap)

**Success Criteria:**

1. OTP verification codes are sent via Telegram when the user is linking a Telegram account
2. The routing decision uses the channel_identities table to determine delivery channel
3. No fallback to WhatsApp for Telegram OTP codes

**Plans**: TBD

---

### Tier 8 — Observability

### Phase 26: Agent-Run Tracing & Quality Alerts

**Goal**: Every agent turn produces a structured trace (channel, user, latency, tokens, tool calls, errors) shipped to OpenObserve, with quality alerts that file Forgejo incidents.

**Depends on**: Phase 9 (WhatsApp incident path), Phase 17 (reliability — friendly fallback creates non-error path)

**Requirements**: TBD

**Success Criteria:**

1. Every agent turn emits a structured trace event to OpenObserve
2. "Got stuck" exits (max iterations) are explicitly tagged and alert-worthy
3. OpenObserve dashboard shows p95 latency and tool-error rate over time
4. Alerts on quality metrics flow through ops-bridge → Forgejo issue — same path as crash alerts

**Plans**: TBD

---

### Phase 27: User-Feedback → Incident Loop

**Goal**: A user saying "Nova, that was wrong" (or reacting 👎 on WhatsApp) files a Forgejo issue with the redacted transcript.

**Depends on**: Phase 26 (tracing provides the trace data for the issue body)

**Requirements**: TBD

**Success Criteria:**

1. "Nova, that was wrong" triggers a Forgejo issue with the offending conversation redacted and attached
2. A thumbs-down reaction on a WhatsApp message produces the same result
3. Filed issues contain enough context (user, turn, tool calls, model response) to reproduce
4. Issues are tagged appropriately and become candidates for the eval suite

**Plans**: TBD

---

### Phase 28: Staging Lane & Model Upgrades

**Goal**: A second compose profile (nova-staging, separate DB schema, same GPU) that Coolify deploys first; promotion to production requires clean tests and passing evals.

**Depends on**: Phase 1 (test harness), Phase 7 (eval suite), Phase 26 (tracing provides before/after metrics)

**Requirements**: TBD

**Success Criteria:**

1. Staging compose profile runs alongside production with isolated DB schema on the same GPU
2. Coolify deploys to staging first; promotion to prod requires tests green + evals above threshold
3. Staging can benchmark new models side-by-side with before/after eval reports

**Plans**: TBD

---

### Phase 29: Scheduled Maintenance Agent

**Goal**: Nightly automated dependency/CVE bumps, log-anomaly review, backup verification, and disk/VRAM trend reporting — findings filed as Forgejo issues.

**Depends on**: Phase 1 (test harness for fix branches), Phase 9 (ops-bridge / heal.sh patterns)

**Requirements**: TBD

**Success Criteria:**

1. Nightly headless run checks for outdated dependencies and CVE bumps, producing green-tested fix-ready branches
2. Log-anomaly review surfaces unusual patterns from OpenObserve as Forgejo issues
3. Backup verification restores Postgres dump into scratch container and queries it
4. Disk and VRAM trend report filed as a periodic issue
5. All findings are Forgejo issues; merge requires human approval

**Plans**: TBD

---

### Tier 9 — Advanced Features

### Phase 30: Speaker Identity on Voice

**Goal**: Voice can tell Ruben from Méral — per-room satellite default + voice-embedding identification — so "add it to my list" resolves correctly hands-free.

**Depends on**: Phase 10 (voice channel exists), Phase 13 (DB identity system)

**Requirements**: TBD

**Success Criteria:**

1. Each voice satellite has a per-room default user assignment
2. Voice-embedding speaker verification identifies the speaker; falls back to asking on low confidence
3. Both users can say "what's on *my* plan?" at the same satellite and get their own answers
4. Speaker ID respects existing per-user identity, memory, and preference system

**Plans**: TBD

---

### Phase 31: Per-Person Memory & Privacy Scopes

**Goal**: `remember`/`forget` tools support `private-to-me` vs `household` scope; retrieval is filtered to requester + household scope; dashboard includes a memory browser.

**Depends on**: Phase 4 (memory system in tool backends), Phase 30 (speaker ID ensures correct user attribution for voice)

**Requirements**: TBD

**Success Criteria:**

1. `remember` tool accepts a `scope` parameter (`private` / `household`); defaults to `private` for consistency with voice attribution
2. `forget` tool filters by scope and only forgets what the requester owns
3. Memory retrieval filters to requester memories + household-scope memories
4. A private memory never appears in the other user's answers or briefing
5. Dashboard has a memory browser (view/edit/delete what Nova believes about you)

**Plans**: TBD
**UI hint**: yes

---

### Phase 32: Household Coordination

**Goal**: Message relay between household members, recurring chores with fair-share rotation, and a first-class grocery list distinct from tasks.

**Depends on**: Phase 9 (WhatsApp delivery for relay), Phase 20 (Telegram delivery), Phase 4 (task tooling)

**Requirements**: TBD

**Success Criteria:**

1. "Tell Méral I'll be late" sends an attributed message to the other person's preferred channel
2. Recurring chores with rotation and fair-share nudges are creatable and queryable
3. Grocery list (add-by-voice, auto-dedup, "what do we need?") exists as a distinct entity
4. A relayed message arrives on the other phone; rotating chore alternates assignee correctly

**Plans**: TBD

---

### Phase 33: Proactivity That Respects Attention

**Goal**: Calendar-aware delivery (don't interrupt meetings) and deadline escalation (gentle → day-of → overdue on dashboard).

**Depends on**: Phase 15 (per-user scheduling), Phase 16 (DND windows), Phase 5 (calendar tool), Phase 12 (dashboard — overdue display)

**Requirements**: TBD

**Success Criteria:**

1. Proactive pushes suppressed during calendar events marked busy — Nova does not interrupt a meeting
2. Deadline escalation sends a gentle reminder N days before, firmer on the day-of, dashboard overdue flag after
3. Every proactive push is per-person — same morning produces two different briefings at two different times

**Plans**: TBD

---

### Phase 34: Deeper Email & Calendar Intelligence

**Goal**: Email → action extraction, calendar conflict detection with travel-time warnings, and reply drafting — all local.

**Depends on**: Phase 6 (email tool backends), Phase 5 (calendar tool), Phase 33 (calendar-aware delivery)

**Requirements**: TBD

**Success Criteria:**

1. An invoice email yields a task with the correct due date without user specifying it
2. An invitation email yields a proposed calendar event ("shall I add it?") with confirmation
3. Calendar conflict detection flags overlapping events; warns if travel time is insufficient
4. Reply drafts generated by local LLM, sent via Graph only on explicit confirm

**Plans**: TBD

---

### Phase 35: Home Assistant as a Tool

**Goal**: Add an HA REST API tool to Nova Core so Nova can control lights, thermostat, query presence, and do presence-aware behavior.

**Depends on**: Phase 2 (tool registry/agent loop), Phase 10 (voice channel — to verify presence-aware routing)

**Requirements**: TBD

**Success Criteria:**

1. Nova can turn lights on/off, set thermostat, and query Home Assistant entities via a new tool
2. Nova can check presence ("is Méral home?") via HA
3. Presence-aware: suppress "leave now" nudges when already gone; route voice answers to the speaker's room
4. "Turn off the living-room lights when my meeting starts" works end-to-end

**Plans**: TBD

---

### Phase 36: Write-Action Audit Trail

**Goal**: Every mutating tool call is visible in an activity feed on the dashboard and as a query.

**Depends on**: Phase 8 (write confirmation gate — all mutating tools wired), Phase 12 (dashboard)

**Requirements**: TBD

**Success Criteria:**

1. Activity feed ("what did you change today?") available on the dashboard and as a query
2. Every mutating tool call recorded and visible in the feed
3. Non-destructive reads and queries do not appear in the audit trail

**Plans**: TBD
**UI hint**: yes

---

### Phase 37: Paper & Photo Intake

**Goal**: WhatsApp image → local vision model (or OCR) → structured action: a photo of a school letter becomes a summarized event + task; all processing stays on GPU.

**Depends on**: Phase 9 (WhatsApp inbound media), Phase 4 (task tooling), Phase 5 (calendar tooling)

**Requirements**: PHOTO-IMG, PHOTO-VISION, PHOTO-EXTRACT, PHOTO-CONFIRM

**Success Criteria:**

1. A WhatsApp photo of a letter with a date produces a correct proposed calendar event and task
2. A warranty receipt photo is OCR'd and filed into searchable household documentation *(deferred per CONTEXT.md — SC #2)*
3. All image processing runs locally on the GPU — no cloud vision API calls
4. User confirms extracted actions before creation (extends Phase 8 confirmation pattern)

**Plans**: 2 plans

Plans:
- [ ] 37-01-PLAN.md — Image download & vision analysis pipeline (Wave 1)
- [ ] 37-02-PLAN.md — process_photo tool, confirmation extension, end-to-end wiring & tests (Wave 2)

**UI hint**: yes

---

## Progress

**Execution Order:** Phases execute in numeric order: 1 → 2 → ... → 37

| Phase | Plans | Status | Completed |
|-------|-------|--------|-----------|
| 1. CI/CD & Test Infrastructure | 0/0 | Not started | — |
| 2. Core Agent Loop & Tool Validation | 0/1 | Not started | — |
| 3. Database Connection & Schema Foundation | 0/1 | Not started | — |
| 4. Task Management | 0/0 | Not started | — |
| 5. Calendar Integration | 0/0 | Not started | — |
| 6. Email Integration | 0/0 | Not started | — |
| 7. Evaluation Suite | 0/1 | Not started | — |
| 8. Write Confirmation Gate | 0/0 | Not started | — |
| 9. WhatsApp Channel | 0/0 | Not started | — |
| 10. Voice Channel | 1/1 | Complete    | 2026-07-12 |
| 11. Proactive Scheduler | 1/1 | Complete    | 2026-07-12 |
| 12. Read-Only Dashboard | 1/1 | Complete    | 2026-07-12 |
| 13. DB Preferences & Identity Migration | 1/1 | Complete    | 2026-07-12 |
| 14. WhatsApp OTP Self-Service Linking | 1/1 | Complete    | 2026-07-12 |
| 15. Per-User Dynamic Scheduling | 0/0 | Not started | — |
| 16. Per-User Do Not Disturb | 0/0 | Not started | — |
| 17. Reliability Hardening | 0/0 | Not started | — |
| 18. Security Hardening | 0/0 | Not started | — |
| 19. Channel Adapter & Multi-Channel Schema | 0/0 | Not started | — |
| 20. Telegram Bot Foundation | 0/0 | Not started | — |
| 21. Multi-Channel Identity & Last-Active Tracking | 0/0 | Not started | — |
| 22. Push Gateway Refactor | 0/0 | Not started | — |
| 23. Telegram OTP Self-Service Linking | 0/0 | Not started | — |
| 24. Telegram DND Queuing | 0/0 | Not started | — |
| 25. Direct Telegram OTP Routing | 0/0 | Not started | — |
| 26. Agent-Run Tracing & Quality Alerts | 0/0 | Not started | — |
| 27. User-Feedback → Incident Loop | 0/0 | Not started | — |
| 28. Staging Lane & Model Upgrades | 0/0 | Not started | — |
| 29. Scheduled Maintenance Agent | 0/0 | Not started | — |
| 30. Speaker Identity on Voice | 0/0 | Not started | — |
| 31. Per-Person Memory & Privacy Scopes | 0/0 | Not started | — |
| 32. Household Coordination | 0/0 | Not started | — |
| 33. Proactivity That Respects Attention | 0/0 | Not started | — |
| 34. Deeper Email & Calendar Intelligence | 0/0 | Not started | — |
| 35. Home Assistant as a Tool | 0/0 | Not started | — |
| 36. Write-Action Audit Trail | 0/0 | Not started | — |
| 37. Paper & Photo Intake | 0/2 | In progress | — |
