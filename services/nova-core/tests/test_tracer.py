"""Tests for the tracer module — emit_trace fire-and-forget to OpenObserve."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.tracer import AgentTrace, emit_trace


def _sample_trace(**overrides) -> AgentTrace:
    """Build a realistic AgentTrace for testing."""
    defaults = dict(
        channel="api",
        user="Ruben",
        latency_ms=1234,
        token_count=567,
        tool_calls=[{"name": "add_task", "status": "completed", "duration_ms": 200}],
        errors=[{"tool": "agent", "error": "something went wrong"}],
        iteration_count=2,
        got_stuck=False,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    defaults.update(overrides)
    return AgentTrace(**defaults)


# ------------------------------------------------------------------
# Test 1: emit_trace posts correct payload structure to OpenObserve
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_trace_posts_correct_payload():
    """emit_trace sends all decision-locked fields to the correct URL."""
    trace = _sample_trace()
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.return_value = MagicMock(status_code=200)

    env_patch = {
        "OPENOBSERVE_URL": "http://o2:5080",
        "OPENOBSERVE_ORG": "default",
        "OPENOBSERVE_USER": "admin",
        "OPENOBSERVE_PASSWORD": "password123",
    }

    with patch.dict(os.environ, env_patch, clear=False), \
         patch("httpx.AsyncClient", return_value=mock_client):
        await emit_trace(trace)

    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    url = call_kwargs[0][0]
    assert "/api/default/agent_traces/_json" in url, f"Unexpected URL: {url}"

    json_body = call_kwargs[1]["json"]
    # All decision-locked fields must be present
    for field in ("channel", "user", "latency_ms", "token_count", "tool_calls",
                  "errors", "iteration_count", "got_stuck", "timestamp"):
        assert field in json_body, f"Missing field: {field}"

    assert json_body["channel"] == "api"
    assert json_body["user"] == "Ruben"
    assert json_body["latency_ms"] == 1234
    assert json_body["token_count"] == 567
    assert json_body["got_stuck"] is False
    assert json_body["iteration_count"] == 2


# ------------------------------------------------------------------
# Test 2: emit_trace handles OpenObserve 500 without raising
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_trace_handles_500_silently():
    """emit_trace absorbs a 500 response from OpenObserve without raising."""
    trace = _sample_trace()
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.return_value = httpx.Response(
        status_code=500, request=MagicMock()
    )

    env_patch = {
        "OPENOBSERVE_URL": "http://o2:5080",
        "OPENOBSERVE_ORG": "default",
    }

    with patch.dict(os.environ, env_patch, clear=False), \
         patch("httpx.AsyncClient", return_value=mock_client):
        try:
            await emit_trace(trace)
        except Exception:
            pytest.fail("emit_trace raised an exception on HTTP 500")


# ------------------------------------------------------------------
# Test 3: emit_trace handles connection error without raising
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_trace_handles_connection_error_silently():
    """emit_trace absorbs a ConnectError without raising."""
    trace = _sample_trace()
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.side_effect = httpx.ConnectError("Connection refused")

    env_patch = {
        "OPENOBSERVE_URL": "http://o2:5080",
        "OPENOBSERVE_ORG": "default",
    }

    with patch.dict(os.environ, env_patch, clear=False), \
         patch("httpx.AsyncClient", return_value=mock_client):
        try:
            await emit_trace(trace)
        except Exception:
            pytest.fail("emit_trace raised an exception on ConnectError")


# ------------------------------------------------------------------
# Test 4: emit_trace omitted when OPENOBSERVE_URL not set
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_trace_no_op_when_not_configured():
    """emit_trace does NOT make an HTTP call when OPENOBSERVE_URL is not set."""
    trace = _sample_trace()
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client

    with patch.dict(os.environ, {}, clear=True), \
         patch("httpx.AsyncClient", return_value=mock_client):
        await emit_trace(trace)

    mock_client.post.assert_not_called()
