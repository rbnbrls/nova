---
gsd_state_version: 1.0
milestone: v1
milestone_name: Foundation & Core Features
status: Ready to plan
last_updated: "2026-07-12T13:55:33.000Z"
progress:
  total_phases: 37
  completed_phases: 14
  total_plans: 15
  completed_plans: 14
  percent: 37
stopped_at: null
current_phase: 14
current_phase_name: Phase 14 — WhatsApp OTP Self-Service Linking
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

## Operator Next Steps

- Begin with `/gsd-manager` to view the new dashboard
- Start work on Phase 1: CI/CD & Test Infrastructure
- Old milestone artifacts in `.planning/milestones/` serve as implementation reference
