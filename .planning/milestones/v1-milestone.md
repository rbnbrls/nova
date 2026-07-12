# Milestone v1: milestone

**Status:** ✅ SHIPPED 2026-07-12
**Phases:** 1-37
**Total Plans:** 37 plans

## Overview

Nova — a private, fully local household assistant. Complete rebuild of the agent loop, tool system, database foundation, channel integrations (WhatsApp, Telegram, Voice), proactive scheduling, dashboard, identity management, multi-channel preferences, reliability hardening, observability, and staging infrastructure.

## Phases

### Phase 1: CI/CD & Test Infrastructure
**Goal**: Every subsequent phase is tested from day one.
**Plans**: 1 plan
- [x] 01-01: Establish formal CI/CD test infrastructure

### Phase 2: Core Agent Loop & Tool Validation
**Goal**: Agent loop with tool registration/execution, validation errors.
**Plans**: 1 plan
- [x] 02-01: Core agent loop and tool validation

### Phase 3: Database Connection & Schema Foundation
**Goal**: Persistent Postgres connection pool and core schema.
**Plans**: 1 plan
- [x] 03-01: Database connection pool and schema foundation

### Phase 4: Task Management
**Goal**: Create, list, complete household tasks via natural language.
**Plans**: 1 plan
- [x] 04-01: Task management tools

### Phase 5: Calendar Integration
**Goal**: Create and query calendar events via natural language.
**Plans**: 1 plan
- [x] 05-01: Calendar integration with CalDAV

### Phase 6: Email Integration
**Goal**: Fetch and classify important emails.
**Plans**: 1 plan
- [x] 06-01: Email integration with MS Graph

### Phase 7: Evaluation Suite
**Goal**: Golden-conversation eval suite for tool-calling scenarios.
**Plans**: 1 plan
- [x] 07-01: Evaluation suite

### Phase 8: Write Confirmation Gate
**Goal**: Destructive writes require confirmation before executing.
**Plans**: 1 plan
- [x] 08-01: Write confirmation gate

### Phase 9: WhatsApp Channel
**Goal**: WhatsApp messaging with sender attribution and security.
**Plans**: 1 plan
- [x] 09-01: WhatsApp channel

### Phase 10: Voice Channel
**Goal**: Voice satellite / iPhone voice queries via HA Assist.
**Plans**: 1 plan
- [x] 10-01: Voice channel tests

### Phase 11: Proactive Scheduler
**Goal**: Morning briefings, task reminders, email notifications.
**Plans**: 1 plan
- [x] 11-01: Proactive scheduler

### Phase 12: Read-Only Dashboard
**Goal**: LAN-only static dashboard with SSE data feed.
**Plans**: 1 plan
- [x] 12-01: Read-only dashboard

### Phase 13: DB Preferences & Identity Migration
**Goal**: WhatsApp identity and preferences in Postgres.
**Plans**: 1 plan
- [x] 13-01: DB preferences and identity migration

### Phase 14: WhatsApp OTP Self-Service Linking
**Goal**: Users link WhatsApp via dashboard with OTP verification.
**Plans**: 1 plan
- [x] 14-01: WhatsApp OTP self-service linking

### Phase 15: Per-User Dynamic Scheduling
**Goal**: Each user controls briefing schedule; jobs fire at correct local time.
**Plans**: 1 plan
- [x] 15-01: Per-user dynamic scheduling

### Phase 16: Per-User Do Not Disturb
**Goal**: Proactive pushes respect quiet hours without affecting inbound chat.
**Plans**: 1 plan
- [x] 16-01: Per-user do not disturb

### Phase 17: Reliability Hardening
**Goal**: Chat path survives failures with graceful replies.
**Plans**: 1 plan
- [x] 17-01: Reliability hardening

### Phase 18: Security Hardening
**Goal**: Never trust unauthenticated callers.
**Plans**: 1 plan
- [x] 18-01: Security hardening tests

### Phase 19: Channel Adapter Pattern & Multi-Channel Schema
**Goal**: Multi-channel preferences; WhatsApp conforms to ChannelAdapter.
**Plans**: 1 plan
- [x] 19-01: Channel adapter pattern

### Phase 20: Telegram Bot Foundation
**Goal**: Telegram messaging with full agent-loop parity.
**Plans**: 1 plan
- [x] 20-01: Telegram bot foundation

### Phase 21: Multi-Channel Identity & Last-Active Tracking
**Goal**: Atomic last-active updates; identity resolution across channels.
**Plans**: 1 plan
- [x] 21-01: Multi-channel identity and tracking

### Phase 22: Push Gateway Refactor
**Goal**: All proactive pushes route to last-active channel.
**Plans**: 1 plan
- [x] 22-01: Push gateway refactor

### Phase 23: Telegram OTP Self-Service Linking
**Goal**: Users link Telegram via dashboard with OTP via Telegram.
**Plans**: 1 plan
- [x] 23-01: Telegram OTP linking

### Phase 24: Telegram DND Queuing (Gap Fix)
**Goal**: DND-deferred Telegram alerts deliver correctly.
**Plans**: 1 plan
- [x] 24-01: Telegram DND queuing

### Phase 25: Direct Telegram OTP Routing (Gap Fix)
**Goal**: Telegram OTP codes route through Telegram, not WhatsApp.
**Plans**: 1 plan
- [x] 25-01: Direct Telegram OTP routing

### Phase 26: Agent-Run Tracing & Quality Alerts
**Goal**: Structured traces to OpenObserve with quality alerts.
**Plans**: 1 plan
- [x] 26-01: Agent-run tracing

### Phase 27: User-Feedback → Incident Loop
**Goal**: User feedback triggers Forgejo issues with redacted transcript.
**Plans**: 2 plans
- [x] 27-01: Feedback module
- [x] 27-02: Agent loop and WhatsApp wiring

### Phase 28: Staging Lane & Model Upgrades
**Goal**: Staging compose profile with isolated DB schema.
**Plans**: 2 plans
- [x] 28-01: Staging infrastructure
- [x] 28-02: Promotion gate

### Phase 29: Scheduled Maintenance Agent
**Goal**: Nightly dependency bumps, log review, backup verify, trends.
**Plans**: 3 plans
- [x] 29-01: Foundation
- [x] 29-02: Dep scanner + log anomaly
- [x] 29-03: Backup verify + trend reporter

### Phase 30: Speaker Identity on Voice
**Goal**: Per-room satellite defaults; whoami intent.
**Plans**: 2 plans
- [x] 30-01: Voice room defaults infrastructure
- [x] 30-02: Room-aware endpoint

### Phase 31: Per-Person Memory & Privacy Scopes
**Goal**: Private/household memory scope; retrieval filtering.
**Plans**: 1 plan
- [x] 31-01: Memory privacy scopes

### Phase 32: Household Coordination
**Goal**: Grocery list, message relay, recurring chores.
**Plans**: 2 plans
- [x] 32-01: Grocery list + message relay
- [x] 32-02: Recurring chores

### Phase 33: Proactivity That Respects Attention
**Goal**: Calendar-aware delivery; deadline escalation.
**Plans**: 1 plan
- [x] 33-01: Calendar-gated proactivity

### Phase 34: Deeper Email & Calendar Intelligence
**Goal**: Email action extraction; calendar conflict detection.
**Plans**: 1 plan
- [x] 34-01: Email and calendar intelligence

### Phase 35: Home Assistant as a Tool
**Goal**: HA REST API tools for lights, thermostat, presence.
**Plans**: 1 plan
- [x] 35-01: HA REST API tools

### Phase 36: Write-Action Audit Trail
**Goal**: Activity feed on dashboard for all mutating tool calls.
**Plans**: 1 plan
- [x] 36-01: Write-action audit trail

### Phase 37: Paper & Photo Intake
**Goal**: WhatsApp image → local vision model → structured action.
**Plans**: 1 plan (Wave 1 complete)
- [x] 37-01: Image download + vision analysis

## Milestone Summary

**Key Accomplishments:**
- Full private household assistant with multi-channel support (WhatsApp, Telegram, Voice)
- Local LLM agent loop with 22 registered tools
- Postgres-backed persistent storage (tasks, calendar, email, memories, preferences)
- Proactive scheduling with per-user DND and calendar-aware delivery
- Dashboard with SSE feeds for tasks, events, audit trail, and overdue escalation
- CI/CD with pytest, Ruff linting, mypy type checking, and pre-commit hooks
- Ops infrastructure: staging lane, promotion gate, Forgejo issue filing, OpenObserve tracing
- Security: HMAC auth, OTP verification, rate limiting, channel identity verification

**Technical Details:**
- 188 commits in this branch
- 215 files changed, ~33,000 lines added
- 37 phases, 37+ plans, each with SUMMARY.md and VERIFICATION.md
- All phases verified passed

**Issues Deferred:**
- Phase 37 Plan 2 (process_photo tool + confirmation gate) — deferred to next milestone
- Voice-embedding speaker verification — deferred from Phase 30
- HA WebSocket for real-time state — deferred from Phase 35
- Warranty receipt filing (Phase 37 SC #2) — deferred from Phase 37

---

_For current project status, see .planning/ROADMAP.md_
