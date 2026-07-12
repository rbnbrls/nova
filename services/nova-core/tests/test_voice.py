"""Tests for the Voice Channel — HA proxy endpoint and error handling.

The /v1/chat/completions endpoint is the voice proxy that Home Assistant
Assist calls with transcribed speech. These tests verify the contract
and graceful degradation when downstream services are unavailable.
"""
from __future__ import annotations

import httpx
import pytest

from unittest.mock import AsyncMock, patch


class TestHAProxyEndpoint:
    """HA proxy endpoint contract tests for voice queries via Assist."""

    def test_voice_query_basic(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "You have 3 tasks due today."
            resp = client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "What's on my calendar today?"}]}
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["choices"][0]["message"]["content"] == "You have 3 tasks due today."
            assert data["model"]
            mock_run.assert_called_once_with("What's on my calendar today?", user="household", history=[])

    def test_voice_query_user_attribution(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "Sure, I can help with that."
            resp = client.post(
                "/v1/chat/completions?user=Ruben",
                json={"messages": [{"role": "user", "content": "Add milk to my shopping list"}]}
            )
            assert resp.status_code == 200
            mock_run.assert_called_once_with("Add milk to my shopping list", user="Ruben", history=[])

    def test_voice_query_default_user_fallback(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "Hello! How can I help?"
            resp = client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "Hello"}]}
            )
            assert resp.status_code == 200
            mock_run.assert_called_once_with("Hello", user="household", history=[])

    def test_voice_query_conversation_history(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "I've added it to your task list."
            resp = client.post(
                "/v1/chat/completions",
                json={
                    "messages": [
                        {"role": "user", "content": "What's my plan for today?"},
                        {"role": "assistant", "content": "You have a meeting at 2pm and a task to buy groceries."},
                        {"role": "user", "content": "Add buy milk to my tasks"},
                    ]
                }
            )
            assert resp.status_code == 200
            mock_run.assert_called_once_with(
                "Add buy milk to my tasks",
                user="household",
                history=[
                    {"role": "user", "content": "What's my plan for today?"},
                    {"role": "assistant", "content": "You have a meeting at 2pm and a task to buy groceries."},
                ]
            )


class TestVoiceErrorHandling:
    """Error handling tests — graceful degradation when downstream is unavailable."""

    def test_voice_llm_unavailable_returns_friendly_fallback(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = Exception("Ollama connection refused")
            resp = client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "What's on my calendar?"}]}
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["choices"][0]["message"]["content"] == "Nova is having trouble right now, please try again later."

    def test_voice_llm_timeout_returns_friendly_fallback(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = TimeoutError()
            resp = client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "What's new?"}]}
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["choices"][0]["message"]["content"] == "Nova is having trouble right now, please try again later."

    def test_voice_ha_downstream_unreachable(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = httpx.HTTPStatusError("503 from HA", request=httpx.Request("POST", "/"), response=httpx.Response(503))
            resp = client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "Turn on the kitchen light"}]}
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["choices"][0]["message"]["content"] == "Nova is having trouble right now, please try again later."

    def test_voice_empty_message_handling(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "How can I help?"
            resp = client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": ""}]}
            )
            assert resp.status_code == 200
            mock_run.assert_called_once_with("", user="household", history=[])
