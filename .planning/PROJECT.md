# Nova

## What This Is

Nova is a private, self-hosted household assistant for Ruben & Méral. It runs on a Proxmox GPU server and is reachable by WhatsApp, Telegram, voice (ESPHome satellites + iPhone via Home Assistant), and a LAN dashboard. Each user independently chooses their channels. It keeps a shared household plan — tasks, calendar, and important email from a shared Outlook mailbox — behind a single channel-agnostic agent ("Nova Core").

## Core Value

A private, fully local household assistant that Ruben & Méral can reach by text or voice, keeping a shared plan (tasks, calendar, important email) — reasoning and data never leave the house.

## Current State

**v1 SHIPPED** 2026-07-14 — 47 phases, 56 plans, ~400 commits, 40k+ lines of code.

Nova is a fully operational private household assistant with:
- Multi-channel support (WhatsApp, Telegram, Voice via HA Assist)
- Dashboard chat and admin panel with live model management
- Deterministic auto-scheduler with replanning and risk detection
- Task and calendar intelligence (labels, blockers, free/busy, conflict-aware rescheduling)
- IMAP/SMTP email (fully local, replacing MS Graph)
- CalDAV/CardDAV interoperability via Radicale
- CI/CD with 445+ passing tests, Ruff linting, mypy type checking

Deferred from v1: photo intake tool, voice-embedding speaker verification, HA WebSocket for real-time state, warranty receipt filing.

See `.planning/milestones/v1-milestone.md` for full archive.

## Context

- `docs/roadmap.md` is the original, pre-reorganization plan — superseded by `.planning/ROADMAP.md`
- Household of two (Ruben, Méral) on a single Proxmox VM with an RTX 2000 Blackwell GPU (~16 GB VRAM)
- Current model: Qwen3-14B for chat/tool-calling, nomic-embed-text for embeddings
- Testing: pytest + pytest-asyncio, unittest.mock, fastapi.testclient
- 6 Docker services orchestrated via docker-compose.yml
- 5 Alembic migrations (0011–0015) on top of 0010 base

## Constraints

- **Privacy**: All reasoning and household data stay local — no cloud LLM calls
- **Hardware**: Single GPU (~16 GB VRAM) shared between chat model and Whisper STT
- **Deployment**: Git-push-to-deploy via Coolify — no manual production changes
- **Existing infra**: Home Assistant reused as-is for voice I/O
- **Compliance**: WhatsApp integration uses the official Meta Cloud API

## Key Decisions

| Decision | Rationale | Status |
|----------|-----------|--------|
| Fully local / air-gapped LLM | Privacy is core to household trust | ✓ Good |
| Self-hosted CalDAV (Radicale) | Avoid another cloud dependency | ✓ Good |
| WhatsApp via Meta Cloud API | Reliability/ToS compliance | ✓ Good |
| Coolify for CI/CD | Git-driven deploy without managed PaaS | ✓ Good |
| All DB migrations additive-only | No destructive changes to production data | ✓ Good |
| IMAP/SMTP over MS Graph | Fully local email processing | ✓ Good |
| Deterministic auto-scheduler | Tasks planned into time blocks from deadlines/durations/availability | ✓ Good |
| Replanning engine | Calendar/task changes trigger schedule recomputation | ✓ Good |

## Reference Artifacts

Milestone archives preserved at `.planning/milestones/`:
- `v1-milestone.md` — Full v1 phase list, decisions, tech debt
- `v1-ROADMAP.md` — ROADMAP.md snapshot at v1 completion
- `v1-STATE.md` — STATE.md snapshot at v1 completion
- `v1-REQUIREMENTS.md` — Requirements at v1 completion
- `v1-phases/` — Phase directories (selected phases)
- `v1.1-ROADMAP.md`, `2.0-ROADMAP.md`, `v3.0-ROADMAP.md` — Previous milestone roadmaps

These serve as implementation references when verifying each new phase against the existing codebase during the discuss phase.

## Evolution

This document evolves at phase transitions and milestone boundaries.

---
*Last updated: 2026-07-16 after v1 milestone*
