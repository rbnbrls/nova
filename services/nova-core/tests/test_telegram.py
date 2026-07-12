"""Tests for Telegram channel."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import identity
from app.channels.telegram import (
    TelegramAdapter,
    _chunk_message,
    process_incoming_telegram,
)

client = TestClient(app)


def _make_telegram_update(chat_id: int = 12345678, text: str = "Hello", update_id: int = 1001) -> dict:
    """Build a realistic Telegram Update JSON payload."""
    return {
        "update_id": update_id,
        "message": {
            "message_id": 42,
            "from": {"id": chat_id, "is_bot": False, "first_name": "Test"},
            "chat": {"id": chat_id, "type": "private"},
            "date": 1700000000,
            "text": text,
        }
    }


class TestTelegramWebhook:
    """Tests for POST /webhooks/telegram endpoint."""

    def test_missing_secret_token_returns_401(self):
        resp = client.post(
            "/webhooks/telegram",
            json=_make_telegram_update(),
            headers={}
        )
        assert resp.status_code == 401

    def test_invalid_secret_token_returns_401(self):
        with patch("app.config.settings.telegram_webhook_secret", "expected-secret"):
            resp = client.post(
                "/webhooks/telegram",
                json=_make_telegram_update(),
                headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"}
            )
        assert resp.status_code == 401

    def test_valid_secret_token_returns_accepted(self):
        with patch("app.config.settings.telegram_enabled", True), \
             patch("app.config.settings.telegram_webhook_secret", "valid-secret"), \
             patch("app.main.db_get_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_conn.fetchval.return_value = None
            mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
            resp = client.post(
                "/webhooks/telegram",
                json=_make_telegram_update(),
                headers={"X-Telegram-Bot-Api-Secret-Token": "valid-secret"}
            )
        assert resp.status_code == 200
        assert resp.json() == {"status": "accepted"}

    def test_disabled_channel_returns_404(self):
        with patch("app.config.settings.telegram_enabled", False):
            resp = client.post(
                "/webhooks/telegram",
                json=_make_telegram_update(),
                headers={"X-Telegram-Bot-Api-Secret-Token": "any-secret"}
            )
        assert resp.status_code == 404

    def test_invalid_json_body_returns_400(self):
        with patch("app.config.settings.telegram_enabled", True), \
             patch("app.config.settings.telegram_webhook_secret", "secret"):
            resp = client.post(
                "/webhooks/telegram",
                content=b"not-json",
                headers={
                    "X-Telegram-Bot-Api-Secret-Token": "secret",
                    "Content-Type": "application/json",
                }
            )
        assert resp.status_code == 400


class TestChunkMessage:
    """Tests for _chunk_message utility."""

    def test_short_message_no_chunking(self):
        text = "Short message"
        chunks = _chunk_message(text)
        assert chunks == [text]

    def test_chunks_at_paragraph_boundary(self):
        para1 = "A" * 2000
        para2 = "B" * 2000
        text = para1 + "\n\n" + para2
        chunks = _chunk_message(text, max_length=3000)
        assert len(chunks) == 2
        assert chunks[0] == para1
        assert chunks[1] == para2

    def test_exact_boundary_no_chunking(self):
        text = "X" * 4096
        chunks = _chunk_message(text, max_length=4096)
        assert len(chunks) == 1

    def test_long_paragraph_chunks_at_sentence(self):
        long_para = "A" * 2000 + ". " + "B" * 2000
        chunks = _chunk_message(long_para, max_length=2500)
        assert len(chunks) >= 2


class TestTelegramAdapter:
    """Tests for TelegramAdapter class."""

    @pytest.mark.asyncio
    async def test_process_incoming_returns_message(self):
        adapter = TelegramAdapter()
        payload = _make_telegram_update(chat_id=12345678, text="Hello")
        result = await adapter.process_incoming(payload)
        assert result is not None
        assert result.channel == "telegram"
        assert result.sender_id == "12345678"
        assert result.text == "Hello"

    @pytest.mark.asyncio
    async def test_process_incoming_returns_none_for_non_message(self):
        adapter = TelegramAdapter()
        result = await adapter.process_incoming({"update_id": 1})
        assert result is None

    @pytest.mark.asyncio
    async def test_process_incoming_returns_none_for_command(self):
        adapter = TelegramAdapter()
        payload = _make_telegram_update(text="/help")
        result = await adapter.process_incoming(payload)
        assert result is None

    @pytest.mark.asyncio
    async def test_process_incoming_returns_none_for_edited_message(self):
        adapter = TelegramAdapter()
        result = await adapter.process_incoming({"update_id": 2, "edited_message": {"text": "edited"}})
        assert result is None

    @pytest.mark.asyncio
    async def test_send_message_resolves_and_sends(self):
        adapter = TelegramAdapter()
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"channel_id": "87654321"}
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        with patch("app.channels.telegram.get_pool", return_value=mock_pool), \
             patch("app.channels.telegram._send_to_chat_id", new_callable=AsyncMock) as mock_send:
            await adapter.send_message("Ruben", "Hello")
            mock_send.assert_called_once_with("87654321", "Hello", False, "Ruben")

    @pytest.mark.asyncio
    async def test_send_message_handles_missing_chat_id(self):
        adapter = TelegramAdapter()
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        with patch("app.channels.telegram.get_pool", return_value=mock_pool):
            await adapter.send_message("Unknown", "Hello")


class TestProcessIncomingTelegram:
    """Tests for process_incoming_telegram background task."""

    @pytest.mark.asyncio
    async def test_unknown_user_gets_refusal(self):
        with patch("app.channels.telegram.user_from_telegram", new_callable=AsyncMock) as mock_resolve, \
             patch("app.channels.telegram._send_to_chat_id", new_callable=AsyncMock) as mock_send:
            mock_resolve.return_value = identity.HOUSEHOLD
            await process_incoming_telegram(_make_telegram_update())
            mock_send.assert_called_once()
            assert "not authorized" in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_known_user_runs_agent(self):
        with patch("app.channels.telegram.user_from_telegram", new_callable=AsyncMock) as mock_resolve, \
             patch("app.channels.telegram.run_agent", new_callable=AsyncMock) as mock_agent, \
             patch("app.channels.telegram._send_to_chat_id", new_callable=AsyncMock) as mock_send, \
             patch("app.channels.telegram.get_pool") as mock_pool:
            mock_resolve.return_value = identity.User(name="Ruben")
            mock_agent.return_value = "Here's your schedule."
            mock_conn = AsyncMock()
            mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn

            await process_incoming_telegram(_make_telegram_update(text="What's on the calendar?"))
            mock_agent.assert_called_once_with("What's on the calendar?", user="Ruben")
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_command_message_skipped(self):
        with patch("app.channels.telegram._send_to_chat_id", new_callable=AsyncMock) as mock_send:
            await process_incoming_telegram(_make_telegram_update(text="/help"))
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_text_skipped(self):
        with patch("app.channels.telegram._send_to_chat_id", new_callable=AsyncMock) as mock_send:
            await process_incoming_telegram({"update_id": 1, "message": {"chat": {"id": 123}}})
            mock_send.assert_not_called()


class TestTelegramCommands:
    """Tests for Telegram command handling (_handle_telegram_command)."""

    def test_help_command_returns_capabilities(self):
        from app.main import _handle_telegram_command
        result = _handle_telegram_command("/help")
        assert "Nova" in result
        assert "Tasks" in result or "tasks" in result
        assert "Calendar" in result or "calendar" in result
        assert "help" in result.lower()

    def test_tasks_command_returns_placeholder(self):
        from app.main import _handle_telegram_command
        result = _handle_telegram_command("/tasks")
        assert "coming soon" in result.lower() or "Try asking" in result

    def test_settings_command_returns_placeholder(self):
        from app.main import _handle_telegram_command
        result = _handle_telegram_command("/settings")
        assert "coming soon" in result.lower() or "dashboard" in result.lower()

    def test_unknown_command_returns_error(self):
        from app.main import _handle_telegram_command
        result = _handle_telegram_command("/unknown")
        assert "Unknown" in result
        assert "/help" in result


class TestTelegramWebhookDedup:
    """Tests for Telegram webhook deduplication logic."""

    def test_duplicate_update_id_returns_accepted(self):
        from app.main import db_get_pool
        mock_conn = AsyncMock()
        mock_conn.execute.return_value = "INSERT 0 0"
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        with patch("app.config.settings.telegram_enabled", True), \
             patch("app.config.settings.telegram_webhook_secret", "secret"), \
             patch("app.main.db_get_pool", return_value=mock_pool):
            from fastapi.testclient import TestClient
            from app.main import app as main_app
            client2 = TestClient(main_app)
            resp = client2.post(
                "/webhooks/telegram",
                json=_make_telegram_update(update_id=999),
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret"}
            )
        assert resp.status_code == 200
        assert resp.json() == {"status": "accepted"}
