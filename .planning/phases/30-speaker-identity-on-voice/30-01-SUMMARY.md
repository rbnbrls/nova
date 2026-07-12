---
phase: 30-speaker-identity-on-voice
plan: 01
subsystem: api
tags: [voice, identity, postgres, alembic, asyncpg, room-session, ttl]
requires:
  - phase: 29-scheduled-maintenance-agent
    provides: Maintenance config, scheduler patterns
provides:
  - voice_room_defaults DB table (room_id PK, default_user_id FK)
  - RoomSessionManager with TTL-based in-memory per-room active user tracking
  - Seed logic from NOVA_VOICE_ROOM_DEFAULTS env var
affects: [Phase 30-02]
tech-stack:
  added: []
  patterns:
    - Per-room session manager with TTL expiry
    - Fallback chain: active session > DB room default > household
key-files:
  created:
    - services/nova-core/alembic/versions/0005_voice_room_defaults.py
    - services/nova-core/app/voice_rooms.py
  modified:
    - services/nova-core/app/main.py
    - services/nova-core/app/db.py
    - services/nova-core/app/config.py
key-decisions:
  - "Room session TTL set to 30 min (configurable) matching typical voice satellite usage patterns"
  - "Cleanup interval set to 5 min for responsive memory management"
  - "Seed logic follows same asyncpg pattern as WhatsApp/Telegram seed blocks for consistency"
requirements-completed: []
coverage:
  - id: D1
    description: "voice_room_defaults DB table with room_id PK and default_user_id FK"
    verification:
      - kind: unit
        ref: "alembic upgrade head creates table; import check passes"
        status: pass
    human_judgment: false
  - id: D2
    description: "NOVA_VOICE_ROOM_DEFAULTS env var seeds voice_room_defaults on startup"
    verification:
      - kind: other
        ref: "Seed logic in db.py run_migrations() follows existing WhatsApp/Telegram pattern"
        status: pass
    human_judgment: false
  - id: D3
    description: "RoomSessionManager with get_active_user implementing fallback chain"
    verification:
      - kind: unit
        ref: "Unit test: active session > DB default > household"
        status: pass
    human_judgment: false
  - id: D4
    description: "TTL-based session expiry with periodic cleanup"
    verification:
      - kind: unit
        ref: "Unit test: expired session returns household; clear_expired removes old sessions"
        status: pass
    human_judgment: false
  - id: D5
    description: "voice_room_cleanup scheduler job every 5 minutes"
    verification:
      - kind: other
        ref: "Wired in main.py lifespan after existing scheduler jobs"
        status: pass
    human_judgment: false
duration: 12min
completed: 2026-07-12
status: complete
---

# Phase 30 Plan 01: Voice Room Defaults Infrastructure Summary

**Voice room defaults DB table, Alembic migration, seed logic from env var, and RoomSessionManager with TTL-based in-memory session tracking**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-12T16:20:00Z
- **Completed:** 2026-07-12T16:32:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added `nova_voice_room_defaults` env var for comma-separated `room:Name` pairs
- Created Alembic migration 0005 adding `voice_room_defaults` table (room_id TEXT PK, default_user_id UUID FK to users)
- Added seed logic in `db.run_migrations()` that parses the env var and inserts into `voice_room_defaults` with ON CONFLICT DO UPDATE and room_id validation
- Created `RoomSessionManager` in `app/voice_rooms.py` with 3-method API:
  - `get_active_user(room_id)` → fallback chain: active session > DB room default > "household"
  - `set_active_user(room_id, user_name)` → set active user with timestamp
  - `clear_expired()` → remove expired sessions, return count
- Wired `RoomSessionManager` into app lifespan with module-level singleton and 5-minute cleanup scheduler job

## Task Commits

Each task was committed atomically:

1. **Task 1: Add voice room defaults config, migration, and seed logic** - `603997f` (feat)
2. **Task 2: Create RoomSessionManager with TTL-based in-memory session tracking** - `fbb7352` (feat)

## Files Created/Modified

- `services/nova-core/alembic/versions/0005_voice_room_defaults.py` - Alembic migration adding voice_room_defaults table
- `services/nova-core/app/voice_rooms.py` - RoomSessionManager and RoomSession dataclass
- `services/nova-core/app/main.py` - Import, module-level var, lifespan init, cleanup scheduler
- `services/nova-core/app/db.py` - Seed logic in run_migrations() for voice room defaults
- `services/nova-core/app/config.py` - nova_voice_room_defaults env var field

## Decisions Made

- 30-minute session TTL matches typical voice satellite usage patterns (burst interaction, then idle)
- 5-minute cleanup interval balances responsiveness with overhead
- Followed existing asyncpg seed pattern from WhatsApp/Telegram for consistency
- Module-level singleton for voice_room_manager matches scheduler pattern

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. Add `NOVA_VOICE_ROOM_DEFAULTS` to Coolify env vars when deploying.

## Next Phase Readiness

Phase 30-02 can now consume `voice_room_manager` in the chat_completions endpoint for room-aware user resolution. RoomSessionManager is importable and wired.
