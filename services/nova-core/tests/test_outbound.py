"""Tests for outbound WhatsApp message sending."""
from __future__ import annotations

from unittest.mock import ANY, AsyncMock, patch, MagicMock
import pytest

from app.channels.whatsapp import send_whatsapp_message


@pytest.mark.asyncio
async def test_send_whatsapp_message_mock_mode():
    """When settings.whatsapp_access_token is empty, send_whatsapp_message returns mock text."""
    with patch("app.channels.whatsapp.settings.whatsapp_access_token", ""):
        result = await send_whatsapp_message("31612345678", "Hello from Nova")
        assert result is None


@pytest.mark.asyncio
async def test_send_whatsapp_message_with_token():
    """When access token is set, send_whatsapp_message posts to Meta API."""
    with patch("app.channels.whatsapp.settings.whatsapp_access_token", "test-token"), \
         patch("app.channels.whatsapp.settings.whatsapp_phone_number_id", "12345"), \
         patch("app.channels.whatsapp.settings.whatsapp_app_secret", "secret"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200
        result = await send_whatsapp_message("31612345678", "test")
        assert mock_post.called


@pytest.mark.asyncio
async def test_send_whatsapp_message_api_error():
    """When Meta API returns an error, send_whatsapp_message does not raise."""
    with patch("app.channels.whatsapp.settings.whatsapp_access_token", "test-token"), \
         patch("app.channels.whatsapp.settings.whatsapp_phone_number_id", "12345"), \
         patch("app.channels.whatsapp.settings.whatsapp_app_secret", "secret"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 500
        result = await send_whatsapp_message("31612345678", "test")
        assert mock_post.called


@pytest.mark.asyncio
async def test_send_dnd_skipped_for_household():
    """household user defaults to template and skips last_inbound_at query."""
    mock_user = type("User", (), {"name": "household"})()
    with patch("app.channels.whatsapp.settings.whatsapp_access_token", "test-token"), \
         patch("app.channels.whatsapp.settings.whatsapp_phone_number_id", "12345"), \
         patch("app.channels.whatsapp.settings.whatsapp_app_secret", "secret"), \
         patch("app.channels.whatsapp.user_from_whatsapp", new_callable=AsyncMock) as mock_user_from, \
         patch("app.channels.whatsapp.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_user_from.return_value = mock_user
        mock_post.return_value.status_code = 200
        mock_conn = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        result = await send_whatsapp_message("31612345678", "test", proactive=True)
        assert mock_post.called
        assert not mock_conn.fetchrow.called


@pytest.mark.asyncio
async def test_send_within_24h_window_sends_free_form():
    """When last_inbound_at is within 24h, send as free-form text (not template)."""
    mock_user = type("User", (), {"name": "Ruben"})()
    with patch("app.channels.whatsapp.settings.whatsapp_access_token", "test-token"), \
         patch("app.channels.whatsapp.settings.whatsapp_phone_number_id", "12345"), \
         patch("app.channels.whatsapp.settings.whatsapp_app_secret", "secret"), \
         patch("app.channels.whatsapp.user_from_whatsapp", new_callable=AsyncMock) as mock_user_from, \
         patch("app.channels.whatsapp.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_user_from.return_value = mock_user
        mock_post.return_value.status_code = 200
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"last_inbound_at": __import__("datetime").datetime(2026, 7, 12, 12, 0, tzinfo=__import__("datetime").timezone.utc)}
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        result = await send_whatsapp_message("31612345678", "test", proactive=False)
        assert mock_post.called
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["type"] == "text"
        assert payload["text"]["body"] == "test"


@pytest.mark.asyncio
async def test_send_outside_24h_window_sends_template():
    """When last_inbound_at is more than 24h ago, send as template."""
    mock_user = type("User", (), {"name": "Ruben"})()
    with patch("app.channels.whatsapp.settings.whatsapp_access_token", "test-token"), \
         patch("app.channels.whatsapp.settings.whatsapp_phone_number_id", "12345"), \
         patch("app.channels.whatsapp.settings.whatsapp_app_secret", "secret"), \
         patch("app.channels.whatsapp.user_from_whatsapp", new_callable=AsyncMock) as mock_user_from, \
         patch("app.channels.whatsapp.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_user_from.return_value = mock_user
        mock_post.return_value.status_code = 200
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"last_inbound_at": __import__("datetime").datetime(2026, 7, 10, 10, 0, tzinfo=__import__("datetime").timezone.utc)}
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        result = await send_whatsapp_message("31612345678", "test", proactive=False)
        assert mock_post.called
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["type"] == "template"
        assert payload["template"]["name"] == "household_update"


@pytest.mark.asyncio
async def test_send_24h_compliance_no_recent_inbound():
    """When last_inbound_at is NULL, send as template."""
    mock_user = type("User", (), {"name": "Ruben"})()
    with patch("app.channels.whatsapp.settings.whatsapp_access_token", "test-token"), \
         patch("app.channels.whatsapp.settings.whatsapp_phone_number_id", "12345"), \
         patch("app.channels.whatsapp.settings.whatsapp_app_secret", "secret"), \
         patch("app.channels.whatsapp.user_from_whatsapp", new_callable=AsyncMock) as mock_user_from, \
         patch("app.channels.whatsapp.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_user_from.return_value = mock_user
        mock_post.return_value.status_code = 200
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"last_inbound_at": None}
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        result = await send_whatsapp_message("31612345678", "test", proactive=False)
        assert mock_post.called
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["type"] == "template"
        assert payload["template"]["name"] == "household_update"
