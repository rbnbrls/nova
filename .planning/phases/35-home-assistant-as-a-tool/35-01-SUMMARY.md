---
phase: 35
plan: 01
subsystem: nova-core
tags: ["home-assistant", "tools", "confirmation-gate", "audit", "httpx"]
status: complete
completed: "2026-07-12T14:25:00Z"
duration: "3m 0s"
requires: [phase-02, phase-08, phase-36]
provides: [HA-01, HA-02, HA-03, HA-04]
affects: [config, tools, agent]
tech-stack:
  added: ["httpx (already present)"]
  patterns: ["@tool decorator", "async HTTP client", "bearer token auth"]
key-files:
  created:
    - services/nova-core/app/tools/home_assistant.py
    - services/nova-core/tests/test_ha.py
  modified:
    - services/nova-core/app/config.py
    - services/nova-core/app/tools/__init__.py
    - services/nova-core/app/agent.py
decisions:
  - D-01: HA REST API with Long-Lived Access Token (env vars NOVA_HA_TOKEN / NOVA_HA_URL)
  - D-02: Three tools: ha_get_state, ha_call_service, ha_query_presence
  - D-03: Presence checking via person entities in HA
  - D-04: Service-calling tools through Phase 8 confirmation gate
metrics:
  tasks: 3
  files_created: 2
  files_modified: 3
  test_count: 13
---

# Phase 35 Plan 01: Home Assistant REST API Tools — Summary

Adds Home Assistant REST API tools to Nova Core so Nova can query entity state, call HA services (lights, thermostat, scenes, etc.), and check person presence — with confirmation gating for service calls per the Phase 8 pattern.

## Task 1: Add HA config, client, and three tools

- **config.py:** `NOVA_HA_TOKEN` (str, default `""`) and `NOVA_HA_URL` (str, default `"http://homeassistant:8123"`) fields added after the CalDAV block.
- **tools/home_assistant.py:** New module with:
  - `_ha_headers()` — Bearer token + Content-Type header builder
  - `_ha_get(path)` — async GET helper with 10s timeout, error handling for HTTPStatusError and RequestError
  - `_ha_post(path, data)` — async POST helper with same error handling
  - `ha_get_state(entity_id)` — queries any HA entity state, returns formatted output with key attributes
  - `ha_call_service(domain, service, target, data)` — calls HA services; body merges entity_id with optional extra data
  - `ha_query_presence(person_name)` — lists/filters person entities from HA state, returns presence status
- **tools/__init__.py:** Added `home_assistant` to the import chain.

**Commit:** `e316cb3`

## Task 2: Wire ha_call_service into confirmation gate + audit

- Added `"ha_call_service"` to `_MAX_MUTATING_TOOLS` set (line 18)
- Added `"ha_call_service"` to the confirmation intercept tuple (line 106)
- Added dedicated `_summarize_action` branch producing `"Called HA service {domain}.{service_name} on {target}"`

**Commit:** `d9cefb8`

## Task 3: Create HA tool tests with httpx mocking

- **tests/test_ha.py:** 13 test scenarios using project-standard `patch("httpx.AsyncClient")` pattern
  - `ha_get_state`: on-state output, 404 error, connection error, unconfigured (no token)
  - `ha_call_service`: turn-on with URL/body verification, with extra data, no target, API error
  - `ha_query_presence`: home, not-home, list-all, no persons, unreachable HA
- All 13 tests pass (0.29s)

**Commit:** `9ca9d50`

## Deviations from Plan

None — plan executed exactly as written.

## Threat Surface

No additional threat surface beyond what was declared in the plan's threat model. All mitigations applied:
- T-35-01 (spoofing): Token stored in env var only (same pattern as Forgejo/WhatsApp)
- T-35-02 (tampering): Service calls through Phase 8 confirmation gate
- T-35-03 (info disclosure): Connection errors return generic messages
- T-35-04 (DoS): 10s timeout, failure returns error string (agent loop continues)

## Known Stubs

None identified. All three tools have full implementation and test coverage.
