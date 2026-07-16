"""Tests for the tracer module — emit_trace fire-and-forget to OpenObserve."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.tracer import AgentTrace, IterationTrace, emit_trace, check_and_alert_slowness, _last_slow_alert


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


# ------------------------------------------------------------------
# Test 5: IterationTrace dataclass fields
# ------------------------------------------------------------------


def test_iteration_trace_dataclass_fields():
    """IterationTrace has all required fields with correct defaults."""
    it = IterationTrace(
        iteration_num=1,
        llm_time_ms=1234,
        tool_time_ms=567,
        tool_name="add_task",
        prompt_tokens=100,
        completion_tokens=50,
    )
    assert it.iteration_num == 1
    assert it.llm_time_ms == 1234
    assert it.tool_time_ms == 567
    assert it.tool_name == "add_task"
    assert it.prompt_tokens == 100
    assert it.completion_tokens == 50


def test_iteration_trace_defaults():
    """IterationTrace token fields default to 0."""
    it = IterationTrace(
        iteration_num=2,
        llm_time_ms=500,
        tool_time_ms=0,
        tool_name="",
    )
    assert it.prompt_tokens == 0
    assert it.completion_tokens == 0


# ------------------------------------------------------------------
# Test 6: AgentTrace enriched with iterations and turn_id
# ------------------------------------------------------------------


def test_agent_trace_iterations_field():
    """AgentTrace includes turn_id and iterations fields."""
    trace = _sample_trace(turn_id="abc-123", iterations=[{"iteration_num": 1}])
    assert trace.turn_id == "abc-123"
    assert len(trace.iterations) == 1
    assert trace.iterations[0]["iteration_num"] == 1
    # Existing fields still present
    assert trace.channel == "api"
    assert trace.user == "Ruben"
    assert trace.latency_ms == 1234
    assert trace.token_count == 567


def test_agent_trace_iterations_default():
    """AgentTrace iterations and turn_id default to empty."""
    trace = _sample_trace()
    assert trace.turn_id == ""
    assert trace.iterations == []


def test_agent_trace_asdict_includes_new_fields():
    """asdict(AgentTrace) includes turn_id and iterations."""
    trace = _sample_trace(turn_id="uuid-1", iterations=[{"iteration_num": 1}])
    d = trace.__class__.__dict__ if hasattr(trace, "__dataclass_fields__") else {}
    # asdict should include the new fields
    from dataclasses import asdict
    dumped = asdict(trace)
    assert "turn_id" in dumped
    assert dumped["turn_id"] == "uuid-1"
    assert "iterations" in dumped
    assert len(dumped["iterations"]) == 1


# ------------------------------------------------------------------
# Test 7: check_and_alert_slowness detects slowness and calls _file_slow_alert
# ------------------------------------------------------------------

_ORIGINAL_LAST_SLOW: dict[str, float] = {}


@pytest.fixture(autouse=True)
def _reset_slow_alert_cooldown():
    """Reset the module-level cooldown tracker before each test."""
    _last_slow_alert.clear()
    yield


@pytest.mark.asyncio
async def test_slowness_check_calls_file_slow_alert():
    """check_and_alert_slowness calls _file_slow_alert when thresholds are exceeded."""
    trace = _sample_trace(
        latency_ms=35000,  # exceeds 30000 turn threshold
        iterations=[
            {
                "iteration_num": 1,
                "llm_time_ms": 20000,  # exceeds 15000 threshold
                "tool_time_ms": 1000,
                "tool_name": "add_task",
                "prompt_tokens": 100,
                "completion_tokens": 50,
            }
        ],
    )

    mock_file_slow = AsyncMock()
    mock_settings = MagicMock()
    mock_settings.forgejo_url = "https://git.example.com"
    mock_settings.forgejo_token = "valid-token"
    mock_settings.forgejo_repo = "user/repo"
    mock_settings.nova_slow_llm_ms = 15000
    mock_settings.nova_slow_tool_ms = 5000
    mock_settings.nova_slow_turn_ms = 30000

    with patch("app.tracer._file_slow_alert", mock_file_slow), \
         patch("app.config.settings", mock_settings):
        await check_and_alert_slowness(trace)

        # Should call _file_slow_alert for turn (latency) + llm (iteration) = at least 2
        assert mock_file_slow.await_count >= 2

        # First call should be for "turn" (total latency exceeded)
        turn_call = mock_file_slow.await_args_list[0]
        assert turn_call.args[0] == "turn"

        # Find the LLM call
        llm_calls = [c for c in mock_file_slow.await_args_list if c.args[0] == "llm"]
        assert len(llm_calls) >= 1


# ------------------------------------------------------------------
# Test 8: Cooldown suppresses duplicate slowness alerts
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slowness_check_skips_within_cooldown():
    """Cooldown suppresses duplicate alerts of the same type within 300s."""
    trace = _sample_trace(
        latency_ms=35000,
        iterations=[
            {
                "iteration_num": 1,
                "llm_time_ms": 20000,
                "tool_time_ms": 1000,
                "tool_name": "add_task",
                "prompt_tokens": 100,
                "completion_tokens": 50,
            }
        ],
    )

    # Mock ForgejoClient at the forgejo module level (where the lazy import looks)
    mock_forgejo_client = MagicMock()
    mock_forgejo_client.create_issue = AsyncMock(return_value=42)

    mock_settings = MagicMock()
    mock_settings.forgejo_url = "https://git.example.com"
    mock_settings.forgejo_token = "valid-token"
    mock_settings.forgejo_repo = "user/repo"
    mock_settings.nova_slow_llm_ms = 15000
    mock_settings.nova_slow_tool_ms = 5000
    mock_settings.nova_slow_turn_ms = 30000

    with patch("app.forgejo.ForgejoClient", return_value=mock_forgejo_client), \
         patch("app.config.settings", mock_settings):
        # First call — _file_slow_alert should actually run and create issues
        await check_and_alert_slowness(trace)
        first_count = mock_forgejo_client.create_issue.await_count
        assert first_count >= 1, "First call should have created issues"

        # Second call — cooldown in _last_slow_alert should suppress new issues
        mock_forgejo_client.reset_mock()
        await check_and_alert_slowness(trace)
        second_count = mock_forgejo_client.create_issue.await_count

        # No new issues created on second call (cooldown active)
        assert second_count == 0, \
            "Cooldown should have suppressed duplicate alerts"


# ------------------------------------------------------------------
# Test 9: Slowness check skips when Forgejo not configured
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slowness_check_skips_when_not_configured():
    """check_and_alert_slowness silently skips when forgejo_token is unset."""
    trace = _sample_trace(
        latency_ms=35000,
        iterations=[
            {
                "iteration_num": 1,
                "llm_time_ms": 20000,
                "tool_time_ms": 1000,
                "tool_name": "add_task",
                "prompt_tokens": 100,
                "completion_tokens": 50,
            }
        ],
    )

    mock_forgejo_client = MagicMock()
    mock_forgejo_client.create_issue = AsyncMock(return_value=42)

    mock_settings = MagicMock()
    mock_settings.forgejo_url = ""  # Empty — not configured
    mock_settings.forgejo_token = ""  # Empty — not configured
    mock_settings.forgejo_repo = "user/repo"
    mock_settings.nova_slow_llm_ms = 15000
    mock_settings.nova_slow_tool_ms = 5000
    mock_settings.nova_slow_turn_ms = 30000

    with patch("app.forgejo.ForgejoClient", return_value=mock_forgejo_client), \
         patch("app.config.settings", mock_settings):
        await check_and_alert_slowness(trace)

        # _file_slow_alert should skip before calling ForgejoClient
        # because settings.forgejo_token is empty
        mock_forgejo_client.create_issue.assert_not_called()
