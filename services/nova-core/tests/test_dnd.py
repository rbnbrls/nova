from __future__ import annotations

import pytest
import zoneinfo
from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from app.identity import is_user_in_dnd, User
from app.channels.whatsapp import send_whatsapp_message
from app.channels.dispatcher import send_to_user
from app.scheduler import process_queued_notifications
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.asyncio
async def test_is_user_in_dnd_overnight():
    # Mock database pool
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch("app.db.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("app.identity.settings") as mock_settings:
         
        mock_settings.nova_timezone = "Europe/Amsterdam"
        mock_get_pool.return_value = mock_pool
        
        # Scenario A: active DND during overnight hours (22:00 - 07:00) at 23:30 local
        mock_conn.fetchrow.return_value = {
            "dnd_enabled": True,
            "dnd_start": time(22, 0),
            "dnd_end": time(7, 0)
        }
        
        fixed_dt_dnd = datetime(2026, 7, 12, 23, 30, tzinfo=zoneinfo.ZoneInfo("Europe/Amsterdam"))
        with patch("app.identity.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_dt_dnd
            res = await is_user_in_dnd("Ruben")
            assert res is True
            
        # Scenario B: inactive DND during overnight hours (22:00 - 07:00) at 12:00 local
        fixed_dt_no_dnd = datetime(2026, 7, 12, 12, 0, tzinfo=zoneinfo.ZoneInfo("Europe/Amsterdam"))
        with patch("app.identity.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_dt_no_dnd
            res = await is_user_in_dnd("Ruben")
            assert res is False


@pytest.mark.asyncio
async def test_proactive_queued_during_dnd():
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch("app.channels.dispatcher.get_pool", new_callable=AsyncMock) as mock_dispatcher_pool, \
         patch("app.channels.whatsapp.get_pool", new_callable=AsyncMock) as mock_whatsapp_pool, \
         patch("app.identity.is_user_in_dnd", new_callable=AsyncMock) as mock_dnd, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
         
        mock_dispatcher_pool.return_value = mock_pool
        mock_whatsapp_pool.return_value = mock_pool
        mock_conn.fetchrow.side_effect = [{"last_active_channel": "whatsapp"}]
        mock_conn.fetchval.side_effect = ["ruben-user-uuid", "31612345678"]
        
        # 1. Proactive send during DND -> Queues, doesn't send HTTP
        mock_dnd.return_value = True
        await send_to_user("Ruben", "Proactive briefing alert", proactive=True)
        
        mock_conn.execute.assert_called_once()
        args = mock_conn.execute.call_args[0]
        assert "INSERT INTO queued_notifications" in args[0]
        assert args[1] == "ruben-user-uuid"
        assert args[2] == "31612345678"
        assert args[3] == "Proactive briefing alert"
        mock_post.assert_not_called()
        
        # Reset mock
        mock_conn.execute.reset_mock()
        mock_conn.fetchrow.side_effect = [{"last_active_channel": "whatsapp"}, {"whatsapp_number": "31612345678"}]
        mock_conn.fetchval.side_effect = ["ruben-user-uuid", "31612345678"]
        
        # 2. Non-proactive send (chatbot reply) during DND -> Bypasses DND, sends HTTP immediately
        mock_dnd.return_value = True
        await send_to_user("Ruben", "Instant bot response", proactive=False)
        mock_conn.execute.assert_not_called()
        # Since settings mock/credentials are unset in testing, it logs to console without http post call, which is correct


def test_dnd_preferences_save_api(client):
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = "ruben-user-uuid"
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        
        resp = client.post(
            "/api/preferences/dnd",
            json={
                "user": "Ruben",
                "dnd_enabled": True,
                "dnd_start": "23:00",
                "dnd_end": "08:00"
            }
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        
        mock_conn.execute.assert_called_once()
        args = mock_conn.execute.call_args[0]
        assert "INSERT INTO user_preferences" in args[0]
        assert "dnd_enabled" in args[0]
        assert args[1] == "ruben-user-uuid"
        assert args[2] is True


@pytest.mark.asyncio
async def test_process_queued_notifications_flush():
    mock_conn = AsyncMock()
    # Return a queued row
    mock_conn.fetch.return_value = [
        {"id": "queue-1", "whatsapp_number": "31612345678", "message_text": "Queued alert text", "name": "Ruben", "channel": "whatsapp"}
    ]
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch("app.db.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("app.identity.is_user_in_dnd", new_callable=AsyncMock) as mock_dnd, \
         patch("app.scheduler.send_whatsapp_message", new_callable=AsyncMock) as mock_send:
         
        mock_get_pool.return_value = mock_pool
        # DND is now ended (False)
        mock_dnd.return_value = False
        
        await process_queued_notifications()
        
        # Verify message sent and deleted from queue
        mock_send.assert_called_once_with("31612345678", "Queued alert text", proactive=False)
        mock_conn.execute.assert_called_once()
        assert "DELETE FROM queued_notifications WHERE id = $1" in mock_conn.execute.call_args[0][0]
        assert mock_conn.execute.call_args[0][1] == "queue-1"
