"""Home Assistant REST API tools.

Provides three @tool-decorated functions that let Nova query entity state,
call HA services (lights, thermostat, scenes, etc.), and check person presence
via the HA REST API with a Long-Lived Access Token.

Requires NOVA_HA_TOKEN and NOVA_HA_URL environment variables.
"""
from __future__ import annotations

import json

import httpx

from .base import tool
from ..config import settings


# ---------------------------------------------------------------------------
# Internal HTTP helpers
# ---------------------------------------------------------------------------


async def _ha_headers() -> dict:
    """Build the Authorization header for HA API calls.

    Returns an empty dict if the token is not configured so callers can
    detect the unconfigured state and return a friendly message.
    """
    if not settings.nova_ha_token:
        return {}
    return {
        "Authorization": f"Bearer {settings.nova_ha_token}",
        "Content-Type": "application/json",
    }


async def _ha_get(path: str) -> dict | list:
    """GET an HA REST API endpoint and return the parsed JSON response."""
    token = settings.nova_ha_token
    if not token:
        return {"error": "HA not configured — set NOVA_HA_TOKEN and NOVA_HA_URL"}

    headers = await _ha_headers()
    url = f"{settings.nova_ha_url.rstrip('/')}/api/{path.lstrip('/')}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        return {"error": f"HA API error {exc.response.status_code}: {exc.response.text}"}
    except httpx.RequestError as exc:
        return {"error": f"HA connection failed: {exc}"}


async def _ha_post(path: str, data: dict | None = None) -> dict | list:
    """POST to an HA REST API endpoint with an optional JSON body."""
    token = settings.nova_ha_token
    if not token:
        return {"error": "HA not configured — set NOVA_HA_TOKEN and NOVA_HA_URL"}

    headers = await _ha_headers()
    url = f"{settings.nova_ha_url.rstrip('/')}/api/{path.lstrip('/')}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, headers=headers, json=data or {})
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        return {"error": f"HA API error {exc.response.status_code}: {exc.response.text}"}
    except httpx.RequestError as exc:
        return {"error": f"HA connection failed: {exc}"}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool(
    name="ha_get_state",
    description="Get the current state and attributes of any Home Assistant entity "
    "by entity_id. Use this to query lights (on/off), sensors (temperature, "
    "humidity), binary sensors (presence, door/window), climate (current "
    "temp/hvac mode), or any HA entity.",
    parameters={
        "type": "object",
        "properties": {
            "entity_id": {
                "type": "string",
                "description": "Entity ID, e.g. light.living_room, "
                "sensor.living_room_temperature, person.ruben, "
                "binary_sensor.front_door",
            },
        },
        "required": ["entity_id"],
    },
)
async def ha_get_state(entity_id: str) -> str:
    """Query the current state of a single HA entity."""
    result = await _ha_get(f"states/{entity_id}")

    if isinstance(result, dict) and "error" in result:
        return str(result["error"])

    if isinstance(result, dict):
        entity = result
        state = entity.get("state", "unknown")
        attrs = entity.get("attributes", {})
        # Format a readable response
        lines = [f"HA state for {entity_id}: {state}"]
        # Show key attributes, filtering out internal HA meta keys
        for key in ("friendly_name", "brightness", "temperature", "hvac_action",
                     "hvac_mode", "humidity", "unit_of_measurement", "device_class",
                     "battery_level", "current", "voltage", "power", "energy",
                     "illuminance", "pressure", "wind_speed"):
            val = attrs.get(key)
            if val is not None:
                lines.append(f"  {key}: {val}")
        return "\n".join(lines)

    return f"HA state for {entity_id}: {result}"


@tool(
    name="ha_call_service",
    description="Call any Home Assistant service. Used to turn lights on/off, "
    "set thermostat temperature, activate scenes, lock doors, etc. "
    "Requires user confirmation before execution (per Phase 8 gate).",
    parameters={
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "description": "Service domain, e.g. light, climate, switch, "
                "scene, lock, cover",
            },
            "service": {
                "type": "string",
                "description": "Service name, e.g. turn_on, turn_off, "
                "set_temperature, activate",
            },
            "target": {
                "type": "string",
                "description": "Target entity_id or area_id, e.g. "
                "light.living_room or area.living_room. May also be omitted "
                "if service targets a device/area differently.",
            },
            "data": {
                "type": "object",
                "description": "Additional service data as key-value pairs, "
                'e.g. {"temperature": 21} for set_temperature',
            },
        },
        "required": ["domain", "service"],
    },
)
async def ha_call_service(
    domain: str,
    service: str,
    target: str | None = None,
    data: dict | None = None,
) -> str:
    """Call an HA service (light, climate, scene, etc).

    This function is routed through the Phase 8 confirmation gate in
    agent.py before execution — see Task 2.
    """
    body: dict = {}
    if target is not None:
        body["entity_id"] = target
    if data is not None:
        body.update(data)

    result = await _ha_post(f"services/{domain}/{service}", body)

    if isinstance(result, dict) and "error" in result:
        return str(result["error"])

    location = f" on {target}" if target else ""
    return f"HA service {domain}.{service} called{location}"


@tool(
    name="ha_query_presence",
    description="Check if a specific person is home or away, based on Home "
    "Assistant person entities and their associated device_trackers. "
    "Omit person_name to list all household members' presence.",
    parameters={
        "type": "object",
        "properties": {
            "person_name": {
                "type": "string",
                "description": "Person name (case-insensitive substring "
                "match), e.g. Ruben, Méral. Omit to list all persons.",
            },
        },
    },
)
async def ha_query_presence(person_name: str | None = None) -> str:
    """Check presence via HA person entities."""
    result = await _ha_get("states")

    if isinstance(result, dict) and "error" in result:
        return str(result["error"])

    if not isinstance(result, list):
        return "Unexpected response from HA."

    # Filter to person entities
    persons = [e for e in result if isinstance(e, dict) and e.get("entity_id", "").startswith("person.")]

    if not persons:
        return "No person entities found in HA."

    # Filter by person_name if given
    if person_name:
        name_lower = person_name.lower()
        matched = []
        for p in persons:
            eid = p.get("entity_id", "").lower()
            fname = p.get("attributes", {}).get("friendly_name", "").lower()
            if name_lower in eid or name_lower in fname:
                matched.append(p)

        if not matched:
            return f"No person found matching '{person_name}'."
        if len(matched) == 1:
            p = matched[0]
            state = p.get("state", "unknown")
            name = p.get("attributes", {}).get("friendly_name", p.get("entity_id", ""))
            if state == "home":
                return f"{name} is home."
            else:
                return f"{name} is not home."
        # Multiple matches — fall through to list format
        persons = matched

    # Format full list
    lines = []
    for p in persons:
        eid = p.get("entity_id", "")
        state = p.get("state", "unknown")
        fname = p.get("attributes", {}).get("friendly_name", eid)
        lines.append(f"{eid}: {state} ({fname})")
    return "\n".join(lines)
