"""Tests for the Home Assistant REST API tools.

Covers ha_get_state, ha_call_service, and ha_query_presence using
the project's existing httpx mocking pattern.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.config import settings
from app.tools.home_assistant import ha_get_state, ha_call_service, ha_query_presence


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _set_ha_config():
    """Set HA config for all tests in this module."""
    settings.nova_ha_url = "http://homeassistant:8123"
    settings.nova_ha_token = "test-token-123"
    yield
    # No cleanup needed — settings revert between sessions


def _mock_ha_response(status_code: int, json_data: object) -> MagicMock:
    """Build a mock httpx.Response with the given status and JSON body."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    if status_code >= 400:
        resp.text = str(json_data)
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"{status_code} error", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


# ------------------------------------------------------------------
# HA-01: ha_get_state
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_state_on():
    """ha_get_state returns formatted state for a light that is on."""
    mock_data = {
        "entity_id": "light.living_room",
        "state": "on",
        "attributes": {
            "brightness": 255,
            "friendly_name": "Living Room Light",
            "icon": "mdi:lightbulb",
        },
    }
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_ctx = MagicMock()
        mock_client = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_ctx
        mock_client.get.return_value = _mock_ha_response(200, mock_data)

        result = await ha_get_state(entity_id="light.living_room")

    assert "light.living_room" in result
    assert "on" in result
    assert "Living Room Light" in result


@pytest.mark.asyncio
async def test_get_state_not_found():
    """ha_get_state returns error when entity does not exist."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_ctx = MagicMock()
        mock_client = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_ctx
        mock_client.get.return_value = _mock_ha_response(404, {"error": "Entity not found"})

        result = await ha_get_state(entity_id="light.nonexistent")

    assert "404" in result or "not found" in result.lower() or "error" in result.lower()


@pytest.mark.asyncio
async def test_get_state_connection_error():
    """ha_get_state returns friendly message when HA is unreachable."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_ctx = MagicMock()
        mock_client = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_ctx
        mock_client.get.side_effect = httpx.RequestError("Connection refused")

        result = await ha_get_state(entity_id="light.living_room")

    assert "connection" in result.lower() or "error" in result.lower()


@pytest.mark.asyncio
async def test_get_state_no_config():
    """ha_get_state returns not-configured message when token is empty."""
    settings.nova_ha_token = ""
    result = await ha_get_state(entity_id="light.living_room")
    assert "not configured" in result.lower()


# ------------------------------------------------------------------
# HA-01: ha_call_service
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_service_turn_on():
    """ha_call_service calls /api/services/light/turn_on with entity_id."""
    mock_data = [{"entity_id": "light.living_room", "state": "on"}]
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_ctx = MagicMock()
        mock_client = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_ctx
        mock_client.post.return_value = _mock_ha_response(200, mock_data)

        result = await ha_call_service(
            domain="light", service="turn_on", target="light.living_room"
        )

    assert "light" in result
    assert "turn_on" in result
    # Verify the POST was called with correct URL and body
    call_url = mock_client.post.call_args[0][0]
    assert "services/light/turn_on" in call_url
    call_body = mock_client.post.call_args[1].get("json", {})
    assert call_body.get("entity_id") == "light.living_room"


@pytest.mark.asyncio
async def test_call_service_with_data():
    """ha_call_service passes additional data dict to the service call."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_ctx = MagicMock()
        mock_client = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_ctx
        mock_client.post.return_value = _mock_ha_response(200, [])

        await ha_call_service(
            domain="climate",
            service="set_temperature",
            target="climate.living_room",
            data={"temperature": 21},
        )

    call_body = mock_client.post.call_args[1].get("json", {})
    assert call_body.get("entity_id") == "climate.living_room"
    assert call_body.get("temperature") == 21


@pytest.mark.asyncio
async def test_call_service_no_target():
    """ha_call_service works without a target (some services don't need entity_id)."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_ctx = MagicMock()
        mock_client = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_ctx
        mock_client.post.return_value = _mock_ha_response(200, [])

        result = await ha_call_service(domain="scene", service="activate")

    assert "scene.activate" in result or "scene" in result


@pytest.mark.asyncio
async def test_call_service_error():
    """ha_call_service returns error on HA failure."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_ctx = MagicMock()
        mock_client = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_ctx
        mock_client.post.return_value = _mock_ha_response(400, {"error": "bad request"})

        result = await ha_call_service(
            domain="light", service="turn_on", target="light.living_room"
        )

    assert "400" in result or "error" in result.lower()


# ------------------------------------------------------------------
# HA-02: ha_query_presence
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_presence_home():
    """ha_query_presence returns 'home' for a person who is present."""
    mock_states = [
        {"entity_id": "person.ruben", "state": "home", "attributes": {"friendly_name": "Ruben"}},
        {"entity_id": "person.meral", "state": "not_home", "attributes": {"friendly_name": "Méral"}},
        {"entity_id": "sun.sun", "state": "above_horizon", "attributes": {}},
    ]
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_ctx = MagicMock()
        mock_client = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_ctx
        mock_client.get.return_value = _mock_ha_response(200, mock_states)

        result = await ha_query_presence(person_name="Ruben")

    assert "home" in result.lower()
    assert "Ruben" in result


@pytest.mark.asyncio
async def test_query_presence_not_home():
    """ha_query_presence returns 'not_home' for an absent person."""
    mock_states = [
        {"entity_id": "person.ruben", "state": "not_home", "attributes": {"friendly_name": "Ruben"}},
    ]
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_ctx = MagicMock()
        mock_client = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_ctx
        mock_client.get.return_value = _mock_ha_response(200, mock_states)

        result = await ha_query_presence(person_name="Ruben")

    assert "not home" in result.lower() or "not_home" in result


@pytest.mark.asyncio
async def test_query_presence_all():
    """ha_query_presence with no args lists all persons."""
    mock_states = [
        {"entity_id": "person.ruben", "state": "home", "attributes": {"friendly_name": "Ruben"}},
        {"entity_id": "person.meral", "state": "not_home", "attributes": {"friendly_name": "Méral"}},
    ]
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_ctx = MagicMock()
        mock_client = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_ctx
        mock_client.get.return_value = _mock_ha_response(200, mock_states)

        result = await ha_query_presence()

    assert "person.ruben" in result
    assert "person.meral" in result
    assert "home" in result
    assert "not_home" in result


@pytest.mark.asyncio
async def test_query_presence_no_persons():
    """ha_query_presence handles HA with zero person entities."""
    mock_states = [
        {"entity_id": "sun.sun", "state": "above_horizon", "attributes": {}},
    ]
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_ctx = MagicMock()
        mock_client = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_ctx
        mock_client.get.return_value = _mock_ha_response(200, mock_states)

        result = await ha_query_presence()

    assert "no person" in result.lower()


@pytest.mark.asyncio
async def test_query_presence_unreachable():
    """ha_query_presence returns error when HA is unreachable."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_ctx = MagicMock()
        mock_client = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_ctx
        mock_client.get.side_effect = httpx.RequestError("HA offline")

        result = await ha_query_presence()

    assert "connection" in result.lower() or "error" in result.lower()
