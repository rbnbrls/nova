"""Tests for the Voice Channel — HA proxy endpoint and error handling.

The /v1/chat/completions endpoint is the voice proxy that Home Assistant
Assist calls with transcribed speech. These tests verify the contract
and graceful degradation when downstream services are unavailable.
"""
from __future__ import annotations

import httpx
import pytest

from unittest.mock import AsyncMock, patch, PropertyMock


class TestHAProxyEndpoint:
    """HA proxy endpoint contract tests for voice queries via Assist."""

    @pytest.mark.skip(reason="Superceded by TestVoiceExistingRegression")
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
            mock_run.assert_called_once_with("What's on my calendar today?", user="household", history=[], channel="api")

    @pytest.mark.skip(reason="Superceded by TestVoiceExistingRegression")
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
            mock_run.assert_called_once_with("Add milk to my shopping list", user="Ruben", history=[], channel="api")

    @pytest.mark.skip(reason="Superceded by TestVoiceExistingRegression")
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
            mock_run.assert_called_once_with("Hello", user="household", history=[], channel="api")

    @pytest.mark.skip(reason="Superceded by TestVoiceExistingRegression")
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
                ],
                channel="api",
            )


class TestVoiceErrorHandling:
    """Error handling tests — graceful degradation when downstream is unavailable."""

    @pytest.mark.skip(reason="Superceded by TestVoiceExistingRegression")
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

    @pytest.mark.skip(reason="Superceded by TestVoiceExistingRegression")
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

    @pytest.mark.skip(reason="Superceded by TestVoiceExistingRegression")
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

    @pytest.mark.skip(reason="Superceded by TestVoiceExistingRegression")
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
            mock_run.assert_called_once_with("", user="household", history=[], channel="api")


class TestVoiceRoomResolution:
    """Room-based user resolution via room query param and body field."""

    def test_room_param_resolves_to_default(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.voice_rooms import RoomSessionManager
        client = TestClient(app)
        mock_mgr = AsyncMock(spec=RoomSessionManager)
        mock_mgr.get_active_user.return_value = "Ruben"
        with patch("app.main.voice_room_manager", mock_mgr):
            with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = "You have 3 tasks due."
                resp = client.post(
                    "/v1/chat/completions?room=living_room",
                    json={"messages": [{"role": "user", "content": "What's on my plan?"}]}
                )
                assert resp.status_code == 200
                mock_run.assert_called_once_with("What's on my plan?", user="Ruben", history=[], channel="api")

    def test_room_param_falls_back_to_household(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.voice_rooms import RoomSessionManager
        client = TestClient(app)
        mock_mgr = AsyncMock(spec=RoomSessionManager)
        mock_mgr.get_active_user.return_value = "household"
        with patch("app.main.voice_room_manager", mock_mgr):
            with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = "Hello!"
                resp = client.post(
                    "/v1/chat/completions?room=unknown_room",
                    json={"messages": [{"role": "user", "content": "Hello"}]}
                )
                assert resp.status_code == 200
                mock_run.assert_called_once_with("Hello", user="household", history=[], channel="api")

    def test_user_query_param_overrides_room(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.voice_rooms import RoomSessionManager
        client = TestClient(app)
        mock_mgr = AsyncMock(spec=RoomSessionManager)
        with patch("app.main.voice_room_manager", mock_mgr):
            with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = "Sure!"
                resp = client.post(
                    "/v1/chat/completions?room=living_room&user=Ruben",
                    json={"messages": [{"role": "user", "content": "Add milk"}]}
                )
                assert resp.status_code == 200
                # Explicit user overrides room resolution
                mock_run.assert_called_once_with("Add milk", user="Ruben", history=[], channel="api")

    def test_room_without_query_uses_body_field(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.voice_rooms import RoomSessionManager
        client = TestClient(app)
        mock_mgr = AsyncMock(spec=RoomSessionManager)
        mock_mgr.get_active_user.return_value = "Meral"
        with patch("app.main.voice_room_manager", mock_mgr):
            with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = "Okay!"
                resp = client.post(
                    "/v1/chat/completions",
                    json={
                        "messages": [{"role": "user", "content": "What's on my plan?"}],
                        "room": "kantoor"
                    }
                )
                assert resp.status_code == 200
                mock_run.assert_called_once_with("What's on my plan?", user="Meral", history=[], channel="api")


class TestVoiceWhoAmIIntent:
    """WhoAmI intent detection: 'I'm X' at voice satellite switches room identity."""

    def test_whoami_claims_identity(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.voice_rooms import RoomSessionManager
        client = TestClient(app)
        mock_mgr = AsyncMock(spec=RoomSessionManager)
        with patch("app.main.voice_room_manager", mock_mgr):
            with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
                resp = client.post(
                    "/v1/chat/completions?room=living_room",
                    json={"messages": [{"role": "user", "content": "I'm Ruben"}]}
                )
                assert resp.status_code == 200
                data = resp.json()
                assert "Okay Ruben" in data["choices"][0]["message"]["content"]
                mock_mgr.set_active_user.assert_called_once_with("living_room", "Ruben")
                mock_run.assert_not_called()

    def test_whoami_switches_to_meral(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.voice_rooms import RoomSessionManager
        client = TestClient(app)
        mock_mgr = AsyncMock(spec=RoomSessionManager)
        with patch("app.main.voice_room_manager", mock_mgr):
            with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
                resp = client.post(
                    "/v1/chat/completions",
                    json={"messages": [{"role": "user", "content": "I'm Méral"}]}
                )
                assert resp.status_code == 200
                data = resp.json()
                assert "Okay Meral" in data["choices"][0]["message"]["content"]
                mock_mgr.set_active_user.assert_called_once_with("default", "Meral")
                mock_run.assert_not_called()

    def test_whoami_respects_room(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.voice_rooms import RoomSessionManager
        client = TestClient(app)
        mock_mgr = AsyncMock(spec=RoomSessionManager)
        with patch("app.main.voice_room_manager", mock_mgr):
            with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
                resp = client.post(
                    "/v1/chat/completions?room=kantoor",
                    json={"messages": [{"role": "user", "content": "I'm Ruben"}]}
                )
                assert resp.status_code == 200
                data = resp.json()
                assert "Okay Ruben" in data["choices"][0]["message"]["content"]
                mock_mgr.set_active_user.assert_called_once_with("kantoor", "Ruben")
                mock_run.assert_not_called()

    def test_whoami_normalizes_accent(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.voice_rooms import RoomSessionManager
        client = TestClient(app)
        mock_mgr = AsyncMock(spec=RoomSessionManager)
        with patch("app.main.voice_room_manager", mock_mgr):
            with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
                resp = client.post(
                    "/v1/chat/completions",
                    json={"messages": [{"role": "user", "content": "I'm Méral"}]}
                )
                assert resp.status_code == 200
                data = resp.json()
                # Accent normalized to "Meral" (DB spelling)
                assert "Okay Meral" in data["choices"][0]["message"]["content"]
                mock_mgr.set_active_user.assert_called_once_with("default", "Meral")

    def test_normal_message_does_not_trigger_whoami(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.voice_rooms import RoomSessionManager
        client = TestClient(app)
        mock_mgr = AsyncMock(spec=RoomSessionManager)
        with patch("app.main.voice_room_manager", mock_mgr):
            with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = "You have 3 tasks."
                resp = client.post(
                    "/v1/chat/completions",
                    json={"messages": [{"role": "user", "content": "what is on my plan today"}]}
                )
                assert resp.status_code == 200
                mock_run.assert_called_once()
                mock_mgr.set_active_user.assert_not_called()


class TestVoiceExistingRegression:
    """Regression tests — copied originals to confirm room parameter doesn't break existing behavior."""

    def test_voice_query_basic(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.voice_rooms import RoomSessionManager
        client = TestClient(app)
        mock_mgr = AsyncMock(spec=RoomSessionManager)
        with patch("app.main.voice_room_manager", mock_mgr):
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
                mock_run.assert_called_once_with("What's on my calendar today?", user="household", history=[], channel="api")

    def test_voice_query_user_attribution(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.voice_rooms import RoomSessionManager
        client = TestClient(app)
        mock_mgr = AsyncMock(spec=RoomSessionManager)
        with patch("app.main.voice_room_manager", mock_mgr):
            with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = "Sure, I can help with that."
                resp = client.post(
                    "/v1/chat/completions?user=Ruben",
                    json={"messages": [{"role": "user", "content": "Add milk to my shopping list"}]}
                )
                assert resp.status_code == 200
                mock_run.assert_called_once_with("Add milk to my shopping list", user="Ruben", history=[], channel="api")

    def test_voice_query_default_user_fallback(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.voice_rooms import RoomSessionManager
        client = TestClient(app)
        mock_mgr = AsyncMock(spec=RoomSessionManager)
        with patch("app.main.voice_room_manager", mock_mgr):
            with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = "Hello! How can I help?"
                resp = client.post(
                    "/v1/chat/completions",
                    json={"messages": [{"role": "user", "content": "Hello"}]}
                )
                assert resp.status_code == 200
                mock_run.assert_called_once_with("Hello", user="household", history=[], channel="api")

    def test_voice_query_conversation_history(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.voice_rooms import RoomSessionManager
        client = TestClient(app)
        mock_mgr = AsyncMock(spec=RoomSessionManager)
        with patch("app.main.voice_room_manager", mock_mgr):
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
                    ],
                    channel="api",
                )

    def test_voice_llm_unavailable_returns_friendly_fallback(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.voice_rooms import RoomSessionManager
        client = TestClient(app)
        mock_mgr = AsyncMock(spec=RoomSessionManager)
        with patch("app.main.voice_room_manager", mock_mgr):
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
        from app.voice_rooms import RoomSessionManager
        client = TestClient(app)
        mock_mgr = AsyncMock(spec=RoomSessionManager)
        with patch("app.main.voice_room_manager", mock_mgr):
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
        from app.voice_rooms import RoomSessionManager
        client = TestClient(app)
        mock_mgr = AsyncMock(spec=RoomSessionManager)
        with patch("app.main.voice_room_manager", mock_mgr):
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
        from app.voice_rooms import RoomSessionManager
        client = TestClient(app)
        mock_mgr = AsyncMock(spec=RoomSessionManager)
        with patch("app.main.voice_room_manager", mock_mgr):
            with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = "How can I help?"
                resp = client.post(
                    "/v1/chat/completions",
                    json={"messages": [{"role": "user", "content": ""}]}
                )
                assert resp.status_code == 200
                mock_run.assert_called_once_with("", user="household", history=[], channel="api")
