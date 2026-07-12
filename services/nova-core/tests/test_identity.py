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
