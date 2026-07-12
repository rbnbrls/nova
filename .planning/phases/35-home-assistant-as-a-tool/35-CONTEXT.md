# Phase 35 Context: Home Assistant as a Tool

## Source
ROADMAP.md Phase 35 goal + success criteria.

## Decisions

### Connection Method
- HA REST API with Long-Lived Access Token
- Token stored in env var `NOVA_HA_TOKEN`, endpoint in `NOVA_HA_URL`
- Follow existing tool patterns (@tool decorator, JSON Schema args)

### Tools to Create
1. `ha_get_state(entity_id)` — query entity state (light on/off, person home/away, temperature)
2. `ha_call_service(domain, service, target, data)` — call any HA service (turn_on, set_temperature)
3. `ha_query_presence(person_name)` — check if a specific person is home

### Presence-Aware Features
- Nova can check if user is home before sending "leave now" nudges
- Voice answers routed to the requesting user's room (requires Phase 30 room mapping)
- All tool calls go through the existing confirmation gate (Phase 8) for service calls

## Deferred Ideas
- HA WebSocket for real-time state subscriptions — future enhancement
- Entity discovery and caching
