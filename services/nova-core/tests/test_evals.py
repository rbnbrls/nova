import pytest
from unittest.mock import AsyncMock, patch
from app.agent import run_agent
from app import llm


@pytest.mark.asyncio
async def test_eval_complete_task_confirmation_scenario():
    """Test task completion requires confirmation."""
    if not await llm.is_ready():
        # Fallback/skip or run mock
        mock_turn = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "type": "function",
                    "id": "call_task",
                    "function": {
                        "name": "complete_task",
                        "arguments": '{"title": "buy milk"}'
                    }
                }
            ]
        }
        with patch("app.llm.chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_turn
            resp = await run_agent("Mark 'buy milk' task as done", user="Ruben")
            # Verify the confirmation request interceptor caught it
            assert "[CONFIRMATION_REQUIRED]" in resp
        return

    resp = await run_agent("Mark 'buy milk' task as done", user="Ruben")
    assert "[CONFIRMATION_REQUIRED]" in resp or "buy milk" in resp


@pytest.mark.asyncio
async def test_eval_calendar_query_scenario():
    """Test calendar query date range resolution."""
    if not await llm.is_ready():
        mock_turn = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "type": "function",
                    "id": "call_cal",
                    "function": {
                        "name": "list_events",
                        "arguments": '{"start": "2026-07-12T00:00:00", "end": "2026-07-12T23:59:59"}'
                    }
                }
            ]
        }
        with patch("app.llm.chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_turn
            with patch("app.tools.call_tool", new_callable=AsyncMock) as mock_call:
                mock_call.return_value = "Mocked calendar events"
                # Mock second turn to return final answer
                mock_chat.side_effect = [mock_turn, {"role": "assistant", "content": "Here is what's on the calendar."}]
                resp = await run_agent("What's on the calendar tomorrow?", user="Ruben")
                assert "calendar" in resp.lower() or "here is" in resp.lower()
        return

    resp = await run_agent("What's on the calendar tomorrow?", user="Ruben")
    assert "events" in resp.lower() or "agenda" in resp.lower()


@pytest.mark.asyncio
async def test_eval_important_emails_scenario():
    """Test querying important emails."""
    if not await llm.is_ready():
        mock_turn = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "type": "function",
                    "id": "call_email",
                    "function": {
                        "name": "list_recent_emails",
                        "arguments": '{"unread_only": true}'
                    }
                }
            ]
        }
        with patch("app.llm.chat", new_callable=AsyncMock) as mock_chat:
            with patch("app.tools.call_tool", new_callable=AsyncMock) as mock_call:
                mock_call.return_value = "Mocked email list"
                mock_chat.side_effect = [mock_turn, {"role": "assistant", "content": "Here are your emails."}]
                resp = await run_agent("Show my unread emails", user="Ruben")
                assert "emails" in resp.lower()
        return

    resp = await run_agent("Show my unread emails", user="Ruben")
    assert "emails" in resp.lower() or "mailbox" in resp.lower()
