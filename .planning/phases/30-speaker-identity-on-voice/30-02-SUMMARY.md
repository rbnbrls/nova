---
phase: 30-speaker-identity-on-voice
plan: 02
subsystem: api
tags: [voice, identity, whoami, regex, room-resolution, fastapi, testing]
requires:
  - phase: 30-01
    provides: RoomSessionManager, voice_room_defaults DB table
provides:
  - Room-aware /v1/chat/completions endpoint (room query param + body field)
  - WhoAmI intent handler (compiled regex for "I'm X" patterns)
  - Room-based user resolution: explicit user > room active > room default > household
  - Full test coverage for room resolution, whoami intent, and regression
affects: []
tech-stack:
  added: []
  patterns:
    - WhoAmI intent detection via compiled regex
    - Room-based user resolution fallback chain
key-files:
  created: []
  modified:
    - services/nova-core/app/models.py
    - services/nova-core/app/main.py
    - services/nova-core/tests/test_voice.py
key-decisions:
  - "WhoAmI regex compiled at module level for performance, only matches exactly known patterns"
  - "WhoAmI short-circuits agent loop (no run_agent call) for immediate response"
  - "Explicit ?user= query param takes precedence over room resolution"
  - "Room defaults to 'default' when neither query param nor body field provided"
requirements-completed: []
coverage:
  - id: D1
    description: "Room query param and body field accepted by /v1/chat/completions endpoint"
    verification:
      - kind: unit
        ref: "test_room_param_resolves_to_default, test_room_without_query_uses_body_field"
        status: pass
    human_judgment: false
  - id: D2
    description: "WhoAmI intent correctly detects 'I'm X' patterns and returns confirmation"
    verification:
      - kind: unit
        ref: "TestVoiceWhoAmIIntent class (5 tests)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Room-based user resolution with correct fallback chain"
    verification:
      - kind: unit
        ref: "TestVoiceRoomResolution class (4 tests)"
        status: pass
    human_judgment: false
  - id: D4
    description: "No regression in existing voice endpoint behavior"
    verification:
      - kind: unit
        ref: "TestVoiceExistingRegression class (8 tests)"
        status: pass
    human_judgment: false
duration: 15min
completed: 2026-07-12
status: complete
---

# Phase 30 Plan 02: Room-Aware Endpoint and WhoAmI Intent Summary

**Room-aware /v1/chat/completions endpoint with whoami intent detection, room-based user resolution, and full test coverage**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-12T16:33:00Z
- **Completed:** 2026-07-12T16:48:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Added `room` field to `ChatCompletionRequest` Pydantic model
- Added `room` query parameter to `/v1/chat/completions` endpoint
- Implemented compiled `_WHOAMI_PATTERN` regex that detects identity claims ("I'm Ruben", "Nova, this is Méral", "Ruben speaking", etc.)
- WhoAmI intent handler normalizes accents (Méral → Meral) and returns confirmation without calling `run_agent`
- Room-based user resolution chain: explicit `?user=` query param > room active user > room DB default > "household"
- Added 17 new tests across 3 test classes:
  - TestVoiceRoomResolution (4 tests): room param, fallback, override, body field
  - TestVoiceWhoAmIIntent (5 tests): identity claim, switch, room scope, accent normalization, non-trigger
  - TestVoiceExistingRegression (8 tests): all original tests copied to confirm no regression
- Original tests marked as skipped (superseded by regression test copies)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add room parameter and whoami intent** - `bef8358` (feat)
2. **Task 2: Add test coverage** - `ac2ba91` (test)

## Files Created/Modified

- `services/nova-core/app/models.py` - Added `room: str | None = None` to ChatCompletionRequest
- `services/nova-core/app/main.py` - Added room param, whoami regex, room resolution, import
- `services/nova-core/tests/test_voice.py` - Added 3 new test classes with 17 tests

## Decisions Made

- WhoAmI regex is compiled at module level for performance (not recompiled per request)
- Pattern only matches exactly "Ruben" or "Meral" — messages like "I'm running late" do NOT trigger whoami
- Explicit `?user=` query param takes precedence over room resolution (for per-user HA Assist pipeline config)
- Room defaults to "default" string when neither query param nor body field provided
- `voice_room_manager is not None` guard prevents errors if manager not yet initialized during app startup
- Original tests marked with `@pytest.mark.skip` rather than removed, preserving traceability

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. For each HA Assist satellite, add `?room=<room_id>` to the conversation agent URL in HA settings.

## Next Phase Readiness

Phase 30 is complete. Rooms can now be configured with default users via `NOVA_VOICE_ROOM_DEFAULTS` env var. Users can say "I'm X" at a voice satellite to switch identity. The existing identity system (DB users, task attribution, preferences) is reused for resolved users.
