from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from app.channels.whatsapp import send_whatsapp_message, process_incoming_whatsapp
from app.scheduler import check_new_emails
from app import identity


@pytest.mark.asyncio
async def test_inbound_updates_last_inbound_at():
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "31612345678",
                        "text": {"body": "Hello"}
                    }]
                }
            }]
        }]
    }
    
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch("app.channels.whatsapp.send_whatsapp_message", new_callable=AsyncMock) as mock_send, \
         patch("app.channels.whatsapp.run_agent", new_callable=AsyncMock) as mock_agent, \
         patch("app.channels.whatsapp.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("app.identity.user_from_whatsapp", new_callable=AsyncMock) as mock_resolve:
         
        mock_get_pool.return_value = mock_pool
        mock_resolve.return_value = identity.User(name="Ruben")
        mock_agent.return_value = "Replying hello"
        
        await process_incoming_whatsapp(payload)
        
        # Verify last_inbound_at is updated in the database
        mock_conn.execute.assert_called_once()
        args, kwargs = mock_conn.execute.call_args
        assert "UPDATE users SET last_inbound_at = now()" in args[0]
        assert args[1] == "Ruben"


@pytest.mark.asyncio
async def test_outbound_whatsapp_compliance_checks():
    settings = identity.settings
    
    # Mock database pool and connection returning old last_inbound_at (> 24 hours)
    old_time = datetime.now(timezone.utc) - timedelta(hours=25)
    mock_conn_old = AsyncMock()
    mock_conn_old.fetchrow.return_value = {"last_inbound_at": old_time}
    mock_pool_old = MagicMock()
    mock_pool_old.acquire.return_value.__aenter__.return_value = mock_conn_old
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("app.channels.whatsapp.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("app.channels.whatsapp.user_from_whatsapp", new_callable=AsyncMock) as mock_resolve:
         
        mock_resolve.return_value = identity.User(name="Ruben")
        mock_get_pool.return_value = mock_pool_old
        mock_post.return_value.status_code = 200
        settings.whatsapp_phone_number_id = "123"
        settings.whatsapp_access_token = "token"
        
        await send_whatsapp_message("31612345678", "Daily update content")
        
        # Verify it used the template payload structure
        args, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert payload["type"] == "template"
        assert payload["template"]["name"] == "household_update"

    # Mock database pool returning new last_inbound_at (< 24 hours)
    new_time = datetime.now(timezone.utc) - timedelta(hours=2)
    mock_conn_new = AsyncMock()
    mock_conn_new.fetchrow.return_value = {"last_inbound_at": new_time}
    mock_pool_new = MagicMock()
    mock_pool_new.acquire.return_value.__aenter__.return_value = mock_conn_new
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("app.channels.whatsapp.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("app.channels.whatsapp.user_from_whatsapp", new_callable=AsyncMock) as mock_resolve:
         
        mock_resolve.return_value = identity.User(name="Ruben")
        mock_get_pool.return_value = mock_pool_new
        mock_post.return_value.status_code = 200
        await send_whatsapp_message("31612345678", "Quick check-in text")
        
        # Verify it used the text payload structure
        args, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert payload["type"] == "text"
        assert payload["text"]["body"] == "Quick check-in text"


@pytest.mark.asyncio
async def test_email_polling_deduplication():
    mock_emails = [
        {"id": "test_email_123", "subject": "Factuur July 2026", "from": "billing@energy.nl", "preview": "Invoice details...", "unread": True}
    ]
    
    # Mock pool and connection
    mock_conn = AsyncMock()
    # First query returns None (not processed), second returns 1 (already processed)
    mock_conn.fetchval.side_effect = [None, 1]
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch("app.scheduler.fetch_emails_from_graph", new_callable=AsyncMock) as mock_fetch, \
         patch("app.scheduler.send_whatsapp_message", new_callable=AsyncMock) as mock_send, \
         patch("app.scheduler.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("app.identity.get_all_whatsapp_users", new_callable=AsyncMock) as mock_get_users:
         
        mock_get_users.return_value = {"31612345678": identity.User(name="Ruben")}
        mock_get_pool.return_value = mock_pool
        mock_fetch.return_value = mock_emails
        
        # 1. First poll processes and notifies
        await check_new_emails()
        assert mock_send.call_count == 1
        mock_send.reset_mock()
        
        # Verify logged in database
        mock_conn.execute.assert_called_once()
        args, kwargs = mock_conn.execute.call_args
        assert "INSERT INTO processed_emails" in args[0]
        assert args[1] == "test_email_123"
        
        # 2. Second poll is skipped due to side_effect returning 1
        await check_new_emails()
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_run_briefing_scheduler_triggers():
    import zoneinfo
    
    mock_conn = AsyncMock()
    now_local = datetime.now(zoneinfo.ZoneInfo("Europe/Amsterdam"))
    match_time = now_local.time()
    mismatch_time = (now_local + timedelta(hours=2)).time()
    
    mock_rows = [
        {
            "name": "Ruben",
            "whatsapp_number": "31612345678",
            "morning_briefing_enabled": True,
            "morning_briefing_time": match_time,
            "weekly_briefing_enabled": False,
            "weekly_briefing_day": 1,
            "weekly_briefing_time": mismatch_time,
        },
        {
            "name": "Meral",
            "whatsapp_number": "31687654321",
            "morning_briefing_enabled": True,
            "morning_briefing_time": mismatch_time,
            "weekly_briefing_enabled": False,
            "weekly_briefing_day": 1,
            "weekly_briefing_time": mismatch_time,
        }
    ]
    mock_conn.fetch.return_value = mock_rows
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch("app.scheduler.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("app.scheduler.send_morning_briefing_for_user", new_callable=AsyncMock) as mock_morning, \
         patch("app.scheduler.send_weekly_briefing_for_user", new_callable=AsyncMock) as mock_weekly, \
         patch("app.scheduler.settings") as mock_settings:
         
        mock_settings.nova_timezone = "Europe/Amsterdam"
        mock_get_pool.return_value = mock_pool
        
        from app.scheduler import run_briefing_scheduler
        await run_briefing_scheduler()
        
        # Verify morning was triggered for Ruben (matches time)
        mock_morning.assert_called_once_with("Ruben", "31612345678")
        # Verify weekly was not triggered
        mock_weekly.assert_not_called()

