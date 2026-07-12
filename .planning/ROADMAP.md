# Roadmap: Nova

## Overview

Nova is a private, fully local household assistant that Ruben & Méral can reach by text or voice, keeping a shared plan (tasks, calendar, important email) — reasoning and data never leave the house.

## Completed Milestones

### v1 milestone (37 phases)

✅ **SHIPPED** 2026-07-12 — Full private household assistant with multi-channel support.

See [v1 milestone archive](.planning/milestones/v1-milestone.md) for complete phase list, decisions, and tech debt.

Deferred from this milestone:

- Phase 37 Plan 2 (process_photo tool + confirmation gate)
- Voice-embedding speaker verification
- HA WebSocket for real-time state
- Warranty receipt filing

## Backlog

Phases and features not yet assigned to a milestone.

*(No backlog items yet — next milestone TBD via /gsd-new-milestone)*

### Phase 38: subdomain and email

**Goal:** Replace MS Graph email integration with IMAP-based reading and SMTP-based sending, driven by a single NOVA_DOMAIN env var. Add send_email tool. Use IMAP flags for deduplication instead of the processed_emails database table.
**Requirements**: TBD
**Depends on:** Phase 37
**Plans:** 3 plans

Plans:

- [ ] 38-01-PLAN.md — Config fields (nova_domain, imap_*, smtp_*), remove azure_*, add aioimaplib + aiosmtplib
- [ ] 38-02-PLAN.md — Core refactor: IMAP fetch, SMTP send, send_email tool, scheduler adaptation
- [ ] 38-03-PLAN.md — Alembic migration to drop processed_emails, rewrite email and scheduler tests
