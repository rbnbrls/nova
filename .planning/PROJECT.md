# Nova

## What This Is

Nova is a private, self-hosted household assistant for Ruben & Méral. It runs on their own Proxmox GPU server and is reachable by WhatsApp, voice (ESPHome satellites + iPhone via Home Assistant), and a LAN dashboard. It keeps a shared household plan — tasks, calendar, and important email from a shared Outlook mailbox — behind a single channel-agnostic agent ("Nova Core").

## Core Value

A private, fully local household assistant that Ruben & Méral can reach by text or voice, keeping a shared plan (tasks, calendar, important email) — reasoning and data never leave the house.

## Requirements

### Validated

- ✓ Infra foundation: GPU-passthrough container host, Docker, Coolify git-push-to-deploy — Phase 0-1
- ✓ Closed-loop incident management: OpenObserve alerts → ops-bridge → Forgejo issues → automated triage/heal via headless Claude Code — Phase 1
- ✓ Local AI runtime: Ollama (Qwen3-14B candidate) + Postgres/pgvector schema (tasks, memories, messages) — Phase 2
- ✓ Nova Core: FastAPI OpenAI-compatible `/v1/chat/completions`, agent loop with native tool-calling (max 6 iterations), multi-user identity (Ruben/Méral/household) — Phase 3 (tool bodies are stubs)

### Active

- [ ] WhatsApp channel (Meta Cloud API): dedicated business number, webhook signature verification, sender→user attribution, reply via send API
- [ ] Real household tools: tasks in Postgres (attributed, deadlines), CalDAV calendar (read/write), MS Graph email (Mail.Read on shared mailbox, local-LLM "important" classification)
- [ ] Voice channel: HA Assist with Wyoming Whisper (STT, GPU) + Piper (TTS), ESPHome satellite(s) with custom wake word, iPhone via HA Companion Assist
- [ ] Proactive behavior: morning briefing, reminders, important-email push (basic scheduler, not yet per-person tuned)
- [ ] Static LAN dashboard: read-only calendar + active-tasks-with-deadlines view, auto-refresh, grouped by assignee
- [ ] Test harness (Track A1): pytest suite for nova-core (identity, tool registry, agent loop w/ mocked LLM, webhook signature verification) + ops-bridge (dedup/fingerprint); wired into the container build so a red suite blocks a Coolify deploy; `heal.sh` runs it before committing a fix
- [ ] Agent eval suite (Track A2): golden-conversation evals against the real local model (task creation, date parsing, Dutch/English input, multi-tool turns, refusals); run on every change to system prompt / tool specs / model

### Out of Scope

- Cloud LLM calls of any kind — privacy boundary is non-negotiable; reasoning stays on the local GPU
- Track A3-A6 (run tracing/quality alerts, user-feedback→incident loop, staging lane, scheduled maintenance agent) — deferred until real usage exists to harden against, per roadmap sequencing
- Track B1-B8 (speaker ID, per-person memory/privacy scopes, household coordination/relay, tuned per-person proactivity, deeper email/calendar intelligence, HA-as-a-tool, write-action confirmations, photo/paper intake) — deferred until after the voice channel (Phase 6) ships, since they define the individual-user experience on top of it
- Native mobile app — WhatsApp, voice, and the LAN dashboard cover the needed channels
- Replacing Home Assistant — it's reused as-is for voice I/O, not rebuilt

## Context

- `docs/roadmap.md` is the canonical, previously-approved build plan this PROJECT.md formalizes into GSD's phase/requirement structure. `.planning/codebase/` (ARCHITECTURE.md, STACK.md, etc.) documents the current implementation snapshot in detail.
- Household of two (Ruben, Méral) on a single Proxmox VM with an RTX 2000 Blackwell GPU (~16GB VRAM). Home Assistant is already running and is reused only as the voice I/O layer (Wyoming STT/TTS + Assist), not replaced.
- Current model candidates: Qwen3-14B for chat/tool-calling, nomic-embed-text for embeddings. 14B tool-calling reliability is an open risk the roadmap flags for early validation (fallback: 8B or vLLM).
- Tool layer (tasks/calendar/email) has stable function signatures and JSON-Schema specs already (Phase 3) but stub bodies — real implementations must keep signatures in sync when wiring in Postgres/CalDAV/Graph.
- Beyond Phase 8, the existing roadmap defines two extension tracks (A: agentic SDLC hardening, B: per-person user features) — treated as a future milestone here, except A1/A2 which are pulled into this v1 scope per user decision (cheap now, expensive to retrofit after real integrations ship).

## Constraints

- **Privacy**: All reasoning and household data stay local (Ollama on-box); only WhatsApp (Meta Cloud API) and the shared Outlook mailbox (Microsoft Graph) are permitted to touch the public internet. Never introduce cloud-LLM calls.
- **Hardware**: Single GPU (~16GB VRAM) shared between the chat model and Whisper STT — a real ceiling on model size/quantization choices.
- **Deployment**: Git-push-to-deploy via Coolify only (Phase 1) — no manual production changes outside that path.
- **Existing infra**: Home Assistant is reused as-is for voice I/O; do not replace or fork it.
- **Compliance/reliability**: WhatsApp integration uses the official Meta Cloud API (not an unofficial library), per prior decision.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Fully local / air-gapped LLM | Privacy is core to household trust; no prompts or content leave the box | ✓ Good |
| Self-hosted CalDAV for calendar (HA local calendar or Radicale/Nextcloud) | Avoid another cloud dependency | — Pending |
| WhatsApp via Meta Cloud API (official) | Reliability/ToS compliance over unofficial libraries | — Pending |
| Coolify for self-hosted CI/CD | Git-driven deploy without a managed PaaS | ✓ Good |
| Fold Track A1 (tests) + A2 (evals) into v1, ahead of Phase 4/5 | Cheap to add now, expensive to retrofit once real integrations ship; own roadmap flagged this sequencing | — Pending |
| Track A3-A6 and B1-B8 deferred to a future milestone | Need real usage / the voice channel to exist first before they're well-scoped | — Pending |

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
*Last updated: 2026-07-11 after initialization*
