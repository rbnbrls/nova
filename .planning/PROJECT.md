# Nova

## What This Is

Nova is a private, self-hosted household assistant for Ruben & Méral. It runs on a Proxmox GPU server and is reachable by WhatsApp, Telegram, voice (ESPHome satellites + iPhone via Home Assistant), and a LAN dashboard. Each user independently chooses their channels. It keeps a shared household plan — tasks, calendar, and important email from a shared Outlook mailbox — behind a single channel-agnostic agent ("Nova Core").

## Core Value

A private, fully local household assistant that Ruben & Méral can reach by text or voice, keeping a shared plan (tasks, calendar, important email) — reasoning and data never leave the house.

## Requirements

### Validated

- ✓ Infra foundation: GPU-passthrough container host, Docker, Coolify git-push-to-deploy — Phase 0-1
- ✓ Closed-loop incident management: OpenObserve alerts → ops-bridge → Forgejo issues → automated triage/heal — Phase 1
- ✓ Local AI runtime: Ollama (Qwen3-14B candidate) + Postgres/pgvector schema (tasks, memories, messages) — Phase 2
- ✓ Nova Core: FastAPI OpenAI-compatible `/v1/chat/completions`, agent loop with native tool-calling (max 6 iterations), multi-user identity (Ruben/Méral/household) — Phase 3
- ✓ Test harness (Track A1): pytest suite gates Docker builds + Coolify deploys; heal.sh runs tests before committing fixes — Phase 1
- ✓ Agent eval suite (Track A2): golden-conversation evals against real local model — Phase 2
- ✓ Reliability hardening: Ollama retry/backoff, friendly fallback instead of raw 500s, whole-turn wall-clock budget, bounded history truncation — Phase 11
- ✓ Security hardening: chat API caller authentication before trusting `user` attribution, constant-time ops-bridge token compare — Phase 12

### Out of Scope

Explicitly excluded for v1 (deferred to future milestones per roadmap):

- Track A3-A6: Tracing/quality alerts, feedback→incident loop, staging lane, maintenance agent
- Track B1-B8: Speaker ID, per-person memory/privacy scopes, household coordination, HA-as-a-tool, audit trail, photo intake

## Context

- `docs/roadmap.md` is the canonical, previously-approved build plan this PROJECT.md formalizes.
- Household of two (Ruben, Méral) on a single Proxmox VM with an RTX 2000 Blackwell GPU (~16 GB VRAM).
- Current model candidates: Qwen3-14B for chat/tool-calling, nomic-embed-text for embeddings.
- Tool layer has stable function signatures and JSON-Schema specs already (Phase 3) with real implementations.

## Constraints

- **Privacy**: All reasoning and household data stay local — no cloud LLM calls.
- **Hardware**: Single GPU (~16 GB VRAM) shared between chat model and Whisper STT.
- **Deployment**: Git-push-to-deploy via Coolify (Phase 1) — no manual production changes.
- **Existing infra**: Home Assistant is reused as-is for voice I/O.
- **Compliance**: WhatsApp integration uses the official Meta Cloud API.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Fully local / air-gapped LLM | Privacy is core to household trust | ✓ Implemented |
| Self-hosted CalDAV (Radicale) | Avoid another cloud dependency | ✓ Running in compose |
| WhatsApp via Meta Cloud API | Reliability/ToS compliance | ✓ Wired, needs credentials |
| Coolify for CI/CD | Git-driven deploy without managed PaaS | ✓ Implemented |
| Track A1/A2 in v1 scope | Cheap to add now, expensive to retrofit | ✓ Complete |
| v1.1 "User Preferences" | Implement DB-backed settings, self-linking WhatsApp OTP, dynamic briefings scheduling, and DND | ✓ Complete |
| v2.0 "Reliability & Security" | Ollama retry/backoff, friendly fallback, wall-clock budget, chat API auth, constant-time ops-bridge token | ✓ Complete |
| v3.0 "Multi-Channel Support" | Per-user channel choice (Telegram, WhatsApp, or both), Telegram bot, last-active push routing | ○ In Progress |

## Current Milestone: v3.0 Multi-Channel Support

**Goal:** Each household member independently chooses their channels (Telegram, WhatsApp, or both) for both chat and outbound push — with Telegram full-parity to WhatsApp and last-active-channel routing for pushes.

**Target features:**
- Telegram Bot channel with full Nova Core chat parity (agent loop, tools, identity resolution, raw-body HMAC webhook signature verification)
- Per-user channel preferences in Postgres: Telegram-only, WhatsApp-only, or both — extending the existing preferences store
- Last-active-channel tracking: outbound pushes route to whichever channel the user most recently messaged from
- Telegram self-service OTP linking: dashboard sends verification code as a Telegram message, user confirms (same security model as WhatsApp Phase 8)
- Channel-agnostic outbound push: scheduler, briefings, task reminders, and email alerts route to the correct channel per user via a push gateway

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Milestone completed: 2026-07-11 (v1.0). v2.0 completed 2026-07-12. v3.0 "Multi-Channel Support" started 2026-07-12.*