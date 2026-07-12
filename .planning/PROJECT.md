# Nova

## What This Is

Nova is a private, self-hosted household assistant for Ruben & Méral. It runs on a Proxmox GPU server and is reachable by WhatsApp, Telegram, voice (ESPHome satellites + iPhone via Home Assistant), and a LAN dashboard. Each user independently chooses their channels. It keeps a shared household plan — tasks, calendar, and important email from a shared Outlook mailbox — behind a single channel-agnostic agent ("Nova Core").

## Core Value

A private, fully local household assistant that Ruben & Méral can reach by text or voice, keeping a shared plan (tasks, calendar, important email) — reasoning and data never leave the house.

## Build Order

The roadmap has been reorganized from scratch into 37 phases across 10 build tiers. All phases are reset to Not Started. Reference artifacts from previous milestones are preserved in `.planning/milestones/` for verification.

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

## Context

- `docs/roadmap.md` is the original, pre-reorganization plan — superseded by `.planning/ROADMAP.md`
- Household of two (Ruben, Méral) on a single Proxmox VM with an RTX 2000 Blackwell GPU (~16 GB VRAM)
- Current model candidates: Qwen3-14B for chat/tool-calling, nomic-embed-text for embeddings
- Testing: pytest + pytest-asyncio, unittest.mock, fastapi.testclient

## Constraints

- **Privacy**: All reasoning and household data stay local — no cloud LLM calls
- **Hardware**: Single GPU (~16 GB VRAM) shared between chat model and Whisper STT
- **Deployment**: Git-push-to-deploy via Coolify — no manual production changes
- **Existing infra**: Home Assistant reused as-is for voice I/O
- **Compliance**: WhatsApp integration uses the official Meta Cloud API

## Key Decisions

| Decision | Rationale | Status |
|----------|-----------|--------|
| Fully local / air-gapped LLM | Privacy is core to household trust | Implemented in code |
| Self-hosted CalDAV (Radicale) | Avoid another cloud dependency | Running in compose |
| WhatsApp via Meta Cloud API | Reliability/ToS compliance | Wired, needs credentials |
| Coolify for CI/CD | Git-driven deploy without managed PaaS | Implemented |
| All DB migrations additive-only | No destructive changes to production data | Enforced |

## Reference Artifacts

Previous milestone artifacts preserved at `.planning/milestones/`:
- `v1.0-phases/` — Original foundation phase summaries
- `v1.1-phases/` — Phase 7-10 summaries
- `2.0-phases/` — Phase 1-6, 11-12 summaries
- `v3.0-phases/` — Phase 13-17 summaries

These serve as implementation references when verifying each new phase against the existing codebase during the discuss phase.

## Evolution

This document evolves at phase transitions and milestone boundaries.
