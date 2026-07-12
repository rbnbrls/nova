"""Tests for outbound WhatsApp message sending."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

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
