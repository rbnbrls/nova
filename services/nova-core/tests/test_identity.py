from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.identity import user_from_whatsapp, HOUSEHOLD, User, _parse_whatsapp_map
from app.config import settings


def test_parse_whatsapp_map():
    with patch.object(settings, "nova_whatsapp_users", "12345:Ruben, 67890:Meral, invalid_entry"):
        mapping = _parse_whatsapp_map()
        assert mapping["12345"] == User(name="Ruben")
        assert mapping["67890"] == User(name="Meral")
        assert "invalid_entry" not in mapping


@pytest.mark.asyncio
async def test_user_from_whatsapp():
    mock_conn = AsyncMock()
    async def mock_fetchrow(query, number):
        if number == "12345":
            return {"name": "Ruben"}
        return None
    mock_conn.fetchrow.side_effect = mock_fetchrow
    
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch("app.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        
        # Test finding Ruben
        res = await user_from_whatsapp("12345")
        assert res == User(name="Ruben")
        
        # Test leading plus
        res = await user_from_whatsapp("+12345")
        assert res == User(name="Ruben")
        
        # Test unrecognized
        res = await user_from_whatsapp("99999")
        assert res == HOUSEHOLD


# ---------------------------------------------------------------------------
# Phase 9: Identity resolution edge cases
# ---------------------------------------------------------------------------


def test_parse_whatsapp_map_empty_entries():
    with patch.object(settings, "nova_whatsapp_users", "12345:Ruben, , 67890:Meral,,"):
        mapping = _parse_whatsapp_map()
        assert len(mapping) == 2
        assert mapping["12345"] == User(name="Ruben")
        assert mapping["67890"] == User(name="Meral")


def test_parse_whatsapp_map_whitespace():
    with patch.object(settings, "nova_whatsapp_users", "  12345  :  Ruben , 67890:Meral "):
        mapping = _parse_whatsapp_map()
        assert mapping["12345"] == User(name="Ruben")
        assert mapping["67890"] == User(name="Meral")


def test_parse_whatsapp_map_non_ascii_name():
    with patch.object(settings, "nova_whatsapp_users", "12345:Méral"):
        mapping = _parse_whatsapp_map()
        assert mapping["12345"] == User(name="Méral")


def test_parse_whatsapp_map_leading_plus():
    with patch.object(settings, "nova_whatsapp_users", "+12345:Ruben"):
        mapping = _parse_whatsapp_map()
        assert "+12345" in mapping


# ---------------------------------------------------------------------------
# Phase 21: channel_identities resolve() tests
# ---------------------------------------------------------------------------


class TestResolveChannelIdentity:
    """Tests for channels/identity.py resolve()."""

    @pytest.mark.asyncio
    async def test_resolve_returns_user_for_known_channel_id(self):
        from app.channels.identity import resolve
        from app.identity import User

        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"name": "Ruben"}
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        with patch("app.channels.identity.get_pool", return_value=mock_pool):
            result = await resolve("whatsapp", "12345")

        assert result == User(name="Ruben")

    @pytest.mark.asyncio
    async def test_resolve_returns_household_for_unknown(self):
        from app.channels.identity import resolve
        from app.identity import HOUSEHOLD

        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        with patch("app.channels.identity.get_pool", return_value=mock_pool):
            result = await resolve("telegram", "99999")

        assert result is HOUSEHOLD

    @pytest.mark.asyncio
    async def test_resolve_str_channel_id_coercion(self):
        """BIGINT chat_id stored as TEXT — int arg is coerced to str before query."""
        from app.channels.identity import resolve

        call_args = []

        async def fetchrow_spy(query, channel, channel_id):
            call_args.append((channel, channel_id))
            return None

        mock_conn = AsyncMock()
        mock_conn.fetchrow.side_effect = fetchrow_spy
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        with patch("app.channels.identity.get_pool", return_value=mock_pool):
            await resolve("telegram", 12345678)

        # The function should convert int channel_id to str before passing to DB
        assert len(call_args) == 1
        channel, channel_id = call_args[0]
        assert channel == "telegram"
        assert channel_id == "12345678"
        assert isinstance(channel_id, str)
