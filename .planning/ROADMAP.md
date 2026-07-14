# Roadmap: Nova

## Overview

Nova is a private, fully local household assistant that Ruben & Méral can reach by text or voice, keeping a shared plan (tasks, calendar, important email) — reasoning and data never leave the house.

## Completed Milestones

### v1 milestone (47 phases)

✅ **SHIPPED** 2026-07-14 — Full private household assistant with multi-channel support, IMAP/SMTP email, dashboard chat, admin panel with model management, deterministic auto-scheduler, replanning & risk detection, task intelligence, calendar intelligence, and CalDAV/CardDAV interoperability.

See [v1 milestone archive](.planning/milestones/v1-milestone.md) for complete phase list, decisions, and tech debt.

Deferred from this milestone:

- Phase 37 Plan 2 (process_photo tool + confirmation gate)
- Voice-embedding speaker verification
- HA WebSocket for real-time state
- Warranty receipt filing

## Backlog

Phases and features not yet assigned to a milestone.

*(No backlog items yet — next milestone TBD via /gsd-new-milestone)*

## Backlog Notes for the Next Milestone

- CalDAV/CardDAV should be treated as the interoperability contract for the household, with Nova acting as the intelligence layer on top.
- If Outlook needs a bridge rather than native sync for a given household setup, keep that bridge outside Nova Core and document it as a client compatibility concern.
