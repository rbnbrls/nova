---
gsd_state_version: 1.0
milestone: v1
milestone_name: Foundation & Core Features
status: Ready to plan
last_updated: "2026-07-12T16:07:38.395Z"
progress:
  total_phases: 37
  completed_phases: 33
  total_plans: 43
  completed_plans: 39
  percent: 89
stopped_at: null
current_phase: 17
current_phase_name: Phase 17 — Reliability Hardening
current_plan: 01
---

# Project State

## Project Reference

See: `.planning/ROADMAP.md` (reorganized 2026-07-12)

**Core value:** A private, fully local household assistant that Ruben & Méral can reach by text or voice, keeping a shared plan (tasks, calendar, important email) — reasoning and data never leave the house.

**Current focus:** ROADMAP.md entirely reorganized from scratch into 37 phases across 10 build tiers (Tier 0 Foundation → Tier 9 Advanced Features). All phases reset to Not Started.

## Execution Order

Phases execute in strict numeric order: 1 → 2 → ... → 37. Each phase depends on all prior phases.

### Tier 0: Foundation (P1-P3)

  P1 — CI/CD & Test Infrastructure
  P2 — Core Agent Loop & Tool Validation
  P3 — Database Connection & Schema Foundation

### Tier 1: Tool Backends (P4-P8)

  P4 — Task Management
  P5 — Calendar Integration
  P6 — Email Integration
  P7 — Evaluation Suite
  P8 — Write Confirmation Gate

### Tier 2: Channels (P9-P10)

  P9 — WhatsApp Channel
  P10 — Voice Channel

### Tier 3: Proactive & UX (P11-P12)

  P11 — Proactive Scheduler
  P12 — Read-Only Dashboard

### Tier 4: User Management (P13-P16)

  P13 — DB Preferences & Identity Migration
  P14 — WhatsApp OTP Self-Service Linking
  P15 — Per-User Dynamic Scheduling
  P16 — Per-User Do Not Disturb

### Tier 5: Reliability & Security (P17-P18)

  P17 — Reliability Hardening
  P18 — Security Hardening

### Tier 6: Multi-Channel Infrastructure (P19-P22)

  P19 — Channel Adapter & Multi-Channel Schema
  P20 — Telegram Bot Foundation
  P21 — Multi-Channel Identity & Last-Active Tracking
  P22 — Push Gateway Refactor

### Tier 7: Multi-Channel UX (P23-P25)

  P23 — Telegram OTP Self-Service Linking
  P24 — Telegram DND Queuing
  P25 — Direct Telegram OTP Routing

### Tier 8: Observability (P26-P29)

  P26 — Agent-Run Tracing & Quality Alerts
  P27 — User-Feedback → Incident Loop
  P28 — Staging Lane & Model Upgrades
  P29 — Scheduled Maintenance Agent

### Tier 9: Advanced Features (P30-P37)

  P30 — Speaker Identity on Voice
  P31 — Per-Person Memory & Privacy Scopes
  P32 — Household Coordination
  P33 — Proactivity That Respects Attention
  P34 — Deeper Email & Calendar Intelligence
  P35 — Home Assistant as a Tool
  P36 — Write-Action Audit Trail
  P37 — Paper & Photo Intake

## Reference Artifacts

Previous milestone artifacts (v1.0, v1.1, 2.0, v3.0) are preserved under `.planning/milestones/` for code verification reference. The actual codebase already implements features matching the old phase structure — verify each new phase's implementation status against the code during the discuss/plan phase.

## Current Session

**Phase 19: Channel Adapter Pattern & Multi-Channel Schema** — Plan 19-01 completed (2026-07-12)

### Executed Plans

| Plan | Not started |
|------|---------|
| 28-01 | docker-compose.staging.yml, shared nova-net network, staging entrypoint, .env.staging.example |
| 28-02 | ops/promote.sh promotion gate, staging-first deploy.sh, config.env.example with benchmark workflow |
|------|---------|
| 19-01 | Drop unused whatsapp_verification_codes table, formalize ChannelAdapter ABC with register_webhooks, verify SC compliance |
|------|---------|
| 31-01 | Per-person memory privacy scopes — schema, memory tools, agent/briefing integration |
|------|---------|
| 30-01 | Voice room defaults DB table, Alembic migration, seed logic, RoomSessionManager with TTL |
| 30-02 | Room-aware /v1/chat/completions endpoint, whoami intent, room-based user resolution, tests |
| 35-01 | HA REST API tools (ha_get_state, ha_call_service, ha_query_presence), config, confirmation gate, tests |
| 29-01 | ForgejoClient, maintenance subpackage stubs, config, Docker mounts, scheduler wiring |
| 29-02 | Nightly dependency scanner (pip + pip-audit) and log-anomaly reviewer (OpenObserve) |
| 29-03 | Nightly backup verification (scratch Docker container) and weekly trend reporter (disk/VRAM/GPU/Postgres) |
| 18-01 | Auth ordering and error consistency tests for nova-core and ops-bridge |

### Decisions Made

- Room session TTL set to 30 min (configurable) matching typical voice satellite usage patterns
- Cleanup interval set to 5 min for responsive memory management
- Seed logic follows same asyncpg pattern as WhatsApp/Telegram seed blocks for consistency
- WhoAmI regex compiled at module level for performance, only matches exactly known patterns
- WhoAmI short-circuits agent loop (no run_agent call) for immediate response
- Explicit ?user= query param takes precedence over room resolution
- Room defaults to 'default' when neither query param nor body field provided

- Import Request, BackgroundTasks, HTTPException at telegram.py module level so FastAPI can resolve type annotations with `from __future__ import annotations`
- Use module-level `get_pool` in `register_webhooks` handler (already imported) instead of re-importing inside closure

- Each retry attempt logs a warning with attempt number, max retries, exception, and delay — both for HTTPStatusError (5xx) and RequestError branches. (17-01)
- Per-turn wall-clock timeout default raised from 60s to 120s to accommodate up to 3 retries. (17-01)

- ForgejoClient follows ops-bridge's httpx + token-auth + label-resolution pattern
- All maintenance jobs gated by feature toggles (master + per-job)
- Docker socket mounted read-only for security (mitigation T-29-02)
- Log excerpts redacted (IPs, emails, paths) before filing as Forgejo issues (T-29-07)
- Ephemeral scratch containers always cleaned up (even on failure)
- Trend data stored as HTML comment JSON in issue body for machine parsing
- All subprocess calls use async/timeout; no blocking subprocess in async context

- HA REST API with Long-Lived Access Token (env vars NOVA_HA_TOKEN / NOVA_HA_URL)
- Three tools: ha_get_state, ha_call_service, ha_query_presence
- Presence checking via person entities in HA
- Service-calling tools through Phase 8 confirmation gate

- All nova-core auth failure modes return identical `{"detail": "Unauthorized"}` — consistency test proves no attacker-informative differences (18-01)
- Auth ordering test at main.py:141-145 uses AsyncMock to detect run_agent calls — guards against future reordering (18-01)
- ops-bridge app.py:70 uses hmac.compare_digest (constant-time) — existing test proves it (18-01)

- Memory scope defaults to 'private' — users must explicitly opt-in to household sharing (31-01)
- SQL WHERE clause `(user_id = $1 AND scope = 'private') OR scope = 'household'` is the sole privacy enforcement point (31-01)
- `forget` tool requires user confirmation via confirmation gate (like destructive calendar/task ops) (31-01)
- `remember` tool is additive and does NOT need confirmation (31-01)
- Shared memory helper lives in `app/db.py` to avoid circular imports between scheduler and agent (31-01)

- register_webhooks stubs in WhatsAppAdapter and TelegramAdapter are no-ops (pass); actual route migration to webhook_router.py happens in Phase 20 (19-01)

- Shared nova-net bridge network connecting all production + staging containers (28-01)
- Staging entrypoint uses psql with CREATE DATABASE IF NOT EXISTS — idempotent on restart (28-01)
- postgresql-client installed in Dockerfile base stage for both tester and final stage (28-01)
- Internal-only services (postgres, ollama, vector) kept without host ports (28-01)
- promote.sh calls deploy.sh --prod for clean separation of concerns (28-02)
- Deploy default changed to staging-first (--staging) with --prod and --all flags (28-02)
- NOVA_SERVICES fallback ensures backward compatibility (28-02)
- Migration 0007 downgrade recreates whatsapp_verification_codes table exactly; safe rollback with zero data loss (zero rows in production) (19-01)

- Migration `0009` used instead of `0008` for WhatsApp channel_identities backfill because `0008_create_grocery_items.py` already exists (21-01)
- Telegram OTP path also wrapped in `conn.transaction()` for consistency when moving shared `attempts = 99` update into both branches (21-01)

### Last session

**Started:** 2026-07-12T13:57:30Z
**Completed:** 2026-07-12T14:47:00Z
**Plans executed:** 3
**Commits:** f5ef4b1, 26e84b5, ec2b979, e114a30, 8224831

### Prior session

**Started:** 2026-07-12T15:11:16Z
**Completed:** 2026-07-12T17:20:00Z
**Plans executed:** 5 (19-01, 28-01, 28-02, 27-01, 27-02)
**Commits:** 9bd21a6, bf28ce4, 448a7e5, 8171608, 9bbe99a, c97cec9, 9eb2e76, 2ca58cd, eacf997, f507b93, 83a727e, 2356134, d381ae9

### This session

**Started:** 2026-07-12T15:26:55Z
**Completed:** 2026-07-12T15:32:05Z
**Plans executed:** 1 (20-01)
**Commits:** dc69116, d197693

### Session 2026-07-12T15:42:13Z

**Started:** 2026-07-12T15:42:13Z
**Completed:** 2026-07-12T15:44:35Z
**Plans executed:** 1 (23-01)
**Commits:** 0837e8a, 9b5f2a3, 1569d50

### Session 2026-07-12T15:42:43Z

**Started:** 2026-07-12T15:42:43Z
**Completed:** 2026-07-12T16:00:43Z
**Plans executed:** 1 (21-01)
**Commits:** ca72b4d, 2dd7132

### Session 2026-07-12 (Phase 32 — Household Coordination)

**Started:** 2026-07-12T17:42:00Z
**Completed:** 2026-07-12T18:10:00Z
**Plans executed:** 2 (32-01, 32-02)
**Commits:** 0162cc9, 20448ca, 93a4489, a2a8e15, b697b36, 5181623

### Session 2026-07-12 (Phase 15 — Per-User Dynamic Scheduling)

**Started:** 2026-07-12T16:04:54Z
**Completed:** 2026-07-12T16:09:00Z
**Plans executed:** 1 (15-01)
**Commits:** 1d8198d

### Session 2026-07-12 (Phase 16 — Per-User Do Not Disturb)

**Started:** 2026-07-12T16:04:20Z
**Completed:** 2026-07-12T16:06:14Z
**Plans executed:** 1 (16-01)
**Commits:** b005650

## Operator Next Steps

- Next: Phase 33 — Proactivity That Respects Attention
- Old milestone artifacts in `.planning/milestones/` serve as implementation reference
