"""Tests for the voice channel (HA Assist → Nova proxy).

Covers VOICE-01 through VOICE-03: voice query proxy, user attribution,
and error handling when LLM or downstream is unavailable.
"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# HA proxy endpoint tests
# ---------------------------------------------------------------------------


@patch("app.main.run_agent", new_callable=AsyncMock)
def test_voice_query_basic(mock_run):
    """VOICE-01: A voice query returns 200 with a valid response."""
    mock_run.return_value = "Here is your calendar."
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "What's on my calendar?"}]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "choices" in data
    assert data["choices"][0]["message"]["content"] == "Here is your calendar."


@patch("app.main.run_agent", new_callable=AsyncMock)
def test_voice_query_user_attribution(mock_run):
    """VOICE-01: The user query parameter is passed through for speaker ID."""
    mock_run.return_value = "Mocked reply"
    resp = client.post(
        "/v1/chat/completions?user=Meral",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )
    assert resp.status_code == 200
    mock_run.assert_called_once_with("Hello", user="Meral", history=[])


@patch("app.main.run_agent", new_callable=AsyncMock)
def test_voice_query_default_user_fallback(mock_run):
    """VOICE-01: No user parameter defaults to household."""
    mock_run.return_value = "Mocked reply"
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )
    assert resp.status_code == 200
    mock_run.assert_called_once_with("Hello", user="household", history=[])


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


@patch("app.main.run_agent", new_callable=AsyncMock)
def test_voice_llm_unavailable_returns_friendly_fallback(mock_run):
    """VOICE-03: When the LLM raises an exception, return friendly fallback."""
    mock_run.side_effect = Exception("Ollama connection refused")
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "trouble" in data["choices"][0]["message"]["content"].lower()


@patch("app.main.run_agent", new_callable=AsyncMock)
def test_voice_llm_timeout_returns_friendly_fallback(mock_run):
    """VOICE-03: TimeoutError returns friendly fallback instead of 500."""
    mock_run.side_effect = TimeoutError("LLM timed out")
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "trouble" in data["choices"][0]["message"]["content"].lower()


@patch("app.main.run_agent", new_callable=AsyncMock)
def test_voice_ha_downstream_unreachable(mock_run):
    """VOICE-03: Downstream failures return friendly fallback."""
    mock_run.side_effect = ConnectionError("Cannot reach HA")
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "trouble" in data["choices"][0]["message"]["content"].lower()
