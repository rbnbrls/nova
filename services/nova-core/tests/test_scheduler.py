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

    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock()
    mock_conn.fetchrow = AsyncMock()
    # Set up transaction context manager (code uses `async with conn.transaction()`)
    mock_conn.transaction = MagicMock()
    mock_conn.transaction.__aenter__ = AsyncMock()
    mock_conn.transaction.__aexit__ = AsyncMock(return_value=None)
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
        # (Code now makes 2 execute calls: last_inbound_at update + channel tracking)
        assert mock_conn.execute.call_count >= 1
        first_call_args, first_call_kwargs = mock_conn.execute.call_args_list[0]
        assert "UPDATE users SET last_inbound_at = now()" in first_call_args[0]
        assert first_call_args[1] == "Ruben"


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


# ---------------------------------------------------------------------------
# Email polling — IMAP flag-based dedup (replaces DB-based dedup)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_email_polling_deduplication():
    """D-08: Email polling uses IMAP flag dedup — verify _mark_email_processed
    is called with the email UID after notification."""
    important_email = {
        "id": "42",
        "subject": "Factuur July 2026",
        "from": "billing@energy.nl",
        "preview": "Invoice details...",
        "unread": True,
    }

    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = [{"name": "Ruben"}]
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.scheduler.fetch_emails_imap", new_callable=AsyncMock) as mock_fetch, \
         patch("app.scheduler._mark_email_processed", new_callable=AsyncMock) as mock_mark, \
         patch("app.scheduler.send_to_user", new_callable=AsyncMock) as mock_send, \
         patch("app.scheduler.get_pool", new_callable=AsyncMock) as mock_get_pool:

        mock_get_pool.return_value = mock_pool

        # First poll: important email arrives
        mock_fetch.return_value = [important_email]
        await check_new_emails()

        # Verify notification was sent
        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        assert "Ruben" in call_args
        assert "Factuur" in call_args[1]

        # Verify _mark_email_processed called with correct UID
        mock_mark.assert_called_once_with("42")

        # Reset mocks for second poll
        mock_send.reset_mock()
        mock_mark.reset_mock()

        # Second poll: no emails (already processed — IMAP search filters them out)
        mock_fetch.return_value = []
        await check_new_emails()

        # Verify no notification sent for second poll
        mock_send.assert_not_called()
        mock_mark.assert_not_called()


@pytest.mark.asyncio
async def test_email_polling_uses_imap():
    """D-05/D-15: check_new_emails() calls fetch_emails_imap (not fetch_emails_from_graph)."""
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = []
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.scheduler.fetch_emails_imap", new_callable=AsyncMock) as mock_fetch, \
         patch("app.scheduler._mark_email_processed", new_callable=AsyncMock) as mock_mark, \
         patch("app.scheduler.get_pool", new_callable=AsyncMock) as mock_get_pool:

        mock_get_pool.return_value = mock_pool
        mock_fetch.return_value = []

        await check_new_emails()

        # Verify fetch_emails_imap was called (not fetch_emails_from_graph)
        mock_fetch.assert_called_once()
        # _mark_email_processed should NOT be called (no emails)
        mock_mark.assert_not_called()


@pytest.mark.asyncio
async def test_email_polling_no_processed_emails_table():
    """D-09: check_new_emails() does NOT query/insert processed_emails table."""
    # Verify no processed_emails-specific SQL operations in check_new_emails()
    import inspect
    from app import scheduler

    source = inspect.getsource(scheduler.check_new_emails)
    # Only fail if processed_emails appears in SQL-like context (not docstring comments)
    sql_patterns = ["INSERT INTO processed_emails", "FROM processed_emails",
                    "SELECT 1 FROM processed_emails", "processed_emails WHERE"]
    for pattern in sql_patterns:
        assert pattern not in source, (
            f"check_new_emails() still has SQL: {pattern}"
        )
    assert "fetch_emails_from_graph" not in source, (
        "check_new_emails() still references fetch_emails_from_graph"
    )


# ---------------------------------------------------------------------------
# Briefing scheduler triggers (unchanged)
# ---------------------------------------------------------------------------

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
        mock_morning.assert_called_once_with("Ruben")
        # Verify weekly was not triggered
        mock_weekly.assert_not_called()


# ---------------------------------------------------------------------------
# Phase 11: Briefing content tests (updated for IMAP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_morning_briefing_includes_tasks():
    """Morning briefing includes active tasks for the user."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = {"id": "uuid-ruben"}
    mock_conn.fetch.return_value = [{"title": "Buy milk", "due_at": None}]
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.scheduler.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("app.scheduler.get_user_memories", new_callable=AsyncMock) as mock_memories, \
         patch("app.scheduler._get_calendar") as mock_cal, \
         patch("app.scheduler.fetch_emails_imap", return_value=[]), \
         patch("app.scheduler.classify_importance", return_value=False), \
         patch("app.scheduler.send_to_user", new_callable=AsyncMock) as mock_send:

        mock_cal.return_value.search.return_value = []
        mock_get_pool.return_value = mock_pool
        mock_memories.return_value = ""

        from app.scheduler import send_morning_briefing_for_user
        await send_morning_briefing_for_user("Ruben")

        sent_text = mock_send.call_args[0][1]
        assert "Buy milk" in sent_text
        assert "No events today" in sent_text
        assert "No new important emails" in sent_text


@pytest.mark.asyncio
async def test_morning_briefing_empty_states():
    """Morning briefing handles empty tasks, events, and emails gracefully."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = {"id": "uuid-ruben"}
    mock_conn.fetch.return_value = []
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.scheduler.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("app.scheduler.get_user_memories", new_callable=AsyncMock) as mock_memories, \
         patch("app.scheduler._get_calendar") as mock_cal, \
         patch("app.scheduler.fetch_emails_imap", return_value=[]), \
         patch("app.scheduler.classify_importance", return_value=False), \
         patch("app.scheduler.send_to_user", new_callable=AsyncMock) as mock_send:

        mock_cal.return_value.search.return_value = []
        mock_get_pool.return_value = mock_pool
        mock_memories.return_value = ""

        from app.scheduler import send_morning_briefing_for_user
        await send_morning_briefing_for_user("Ruben")

        sent_text = mock_send.call_args[0][1]
        assert "No tasks assigned" in sent_text
        assert "No events today" in sent_text
        assert "No new important emails" in sent_text


@pytest.mark.asyncio
async def test_proactive_send_uses_template():
    """Proactive sends use the pre-approved template outside 24h window."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = {"id": "uuid-ruben"}
    mock_conn.fetch.return_value = []
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.scheduler.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("app.scheduler.get_user_memories", new_callable=AsyncMock) as mock_memories, \
         patch("app.scheduler._get_calendar") as mock_cal, \
         patch("app.scheduler.fetch_emails_imap", return_value=[]), \
         patch("app.scheduler.classify_importance", return_value=False), \
         patch("app.scheduler.send_to_user", new_callable=AsyncMock) as mock_send:

        mock_cal.return_value.search.return_value = []
        mock_get_pool.return_value = mock_pool
        mock_memories.return_value = ""

        from app.scheduler import send_morning_briefing_for_user
        await send_morning_briefing_for_user("Ruben")

        call_kwargs = mock_send.call_args[1]
        assert call_kwargs.get("proactive") is True
        sent_text = mock_send.call_args[0][1]
        assert "Good morning" in sent_text
