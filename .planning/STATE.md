---
gsd_state_version: 1.0
milestone: v1
milestone_name: Foundation & Core Features
status: Milestone complete
last_updated: "2026-07-12T16:50:00Z"
progress:
  total_phases: 37
  completed_phases: 19
  total_plans: 25
  completed_plans: 24
  percent: 51
stopped_at: null
current_phase: 36
current_phase_name: Phase 36 — Write-Action Audit Trail
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

**Phase 30: Speaker Identity on Voice** — Plans 30-01 and 30-02 completed (2026-07-12)

### Executed Plans

| Plan | Summary |
|------|---------|
| 30-01 | Voice room defaults DB table, Alembic migration, seed logic, RoomSessionManager with TTL |
| 30-02 | Room-aware /v1/chat/completions endpoint, whoami intent, room-based user resolution, tests |
| 35-01 | HA REST API tools (ha_get_state, ha_call_service, ha_query_presence), config, confirmation gate, tests |
| 29-01 | ForgejoClient, maintenance subpackage stubs, config, Docker mounts, scheduler wiring |
| 29-02 | Nightly dependency scanner (pip + pip-audit) and log-anomaly reviewer (OpenObserve) |
| 29-03 | Nightly backup verification (scratch Docker container) and weekly trend reporter (disk/VRAM/GPU/Postgres) |

### Decisions Made

- Room session TTL set to 30 min (configurable) matching typical voice satellite usage patterns
- Cleanup interval set to 5 min for responsive memory management
- Seed logic follows same asyncpg pattern as WhatsApp/Telegram seed blocks for consistency
- WhoAmI regex compiled at module level for performance, only matches exactly known patterns
- WhoAmI short-circuits agent loop (no run_agent call) for immediate response
- Explicit ?user= query param takes precedence over room resolution
- Room defaults to 'default' when neither query param nor body field provided

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

### Last session

**Started:** 2026-07-12T13:57:30Z
**Completed:** 2026-07-12T14:47:00Z
**Plans executed:** 3
**Commits:** f5ef4b1, 26e84b5, ec2b979, e114a30, 8224831

### This session

**Started:** 2026-07-12T16:20:00Z
**Completed:** 2026-07-12T16:50:00Z
**Plans executed:** 2 (30-01, 30-02)
**Commits:** 603997f, fbb7352, bef8358, ac2ba91

## Operator Next Steps

- Next: Phase 37 — Paper & Photo Intake
- Old milestone artifacts in `.planning/milestones/` serve as implementation reference
