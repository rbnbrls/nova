# Phase 30 Context: Speaker Identity on Voice

## Source
ROADMAP.md Phase 30 goal + success criteria.

## Decisions

### Approach
- Start with per-room default user assignment (no voice embedding model initially)
- Each voice satellite gets a configured default user (via env var or DB)
- User can switch identity with "Nova, I'm Méral" at the satellite
- Voice-embedding speaker verification deferred to future iteration

### Implementation
- Extend HA proxy endpoint (/v1/chat/completions) to accept a `room` parameter
- Map room → default user via DB table `room_defaults` or config
- `whoami` intent: when user says "I'm X" at a voice satellite, update the room's active user
- Active user session per room in memory (with TTL, falls back to room default)
- Reuse existing identity system (Phase 13) for user resolution

## Deferred Ideas
- Voice-embedding speaker verification model — future enhancement
