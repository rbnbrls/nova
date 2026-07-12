"""Tests for the write-action audit trail (Phase 36)."""
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.audit import record_tool_call
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.asyncio
async def test_record_tool_call():
    """Verify record_tool_call INSERTs with expected parameters and returns the id."""
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = 42
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.audit.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool

        result = await record_tool_call(
            user_name="Ruben",
            tool_name="add_task",
            action_summary="Added task 'Buy milk' for Ruben",
            status="completed",
            confirmation_required=False,
        )

        assert result == 42
        mock_conn.fetchval.assert_called_once()
        call_args = mock_conn.fetchval.call_args[0]
        assert "INSERT INTO audit_log" in call_args[0]
        # Verify the five positional parameters
        params = call_args[1:]
        assert len(params) == 5
        assert params[0] == "Ruben"
        assert params[1] == "add_task"
        assert params[2] == "Added task 'Buy milk' for Ruben"
        assert params[3] == "completed"
        assert params[4] is False


@pytest.mark.skipif(
    not os.environ.get("NOVA_DATABASE_URL"),
    reason="Requires a live Postgres database (set NOVA_DATABASE_URL)",
)
@pytest.mark.asyncio
async def test_record_tool_call_integration():
    """Call record_tool_call against a real DB pool in a rolled-back transaction."""
    import asyncpg
    from app import db
    from app.config import settings

    dsn = os.environ["NOVA_DATABASE_URL"]
    pool = await asyncpg.create_pool(dsn=dsn)

    # Temporarily replace the app pool with our test pool
    original_pool = db._pool
    db._pool = pool

    try:
        async with pool.acquire() as conn:
            await conn.execute("BEGIN")
            try:
                row_id = await record_tool_call(
                    user_name="test_user",
                    tool_name="complete_task",
                    action_summary="Completed task 'Test chore'",
                    status="completed",
                    confirmation_required=True,
                )
                assert row_id is not None
                assert isinstance(row_id, int)

                # Verify the row exists
                row = await conn.fetchrow(
                    "SELECT user_name, tool_name, action_summary, status, confirmation_required FROM audit_log WHERE id = $1",
                    row_id,
                )
                assert row is not None
                assert row["user_name"] == "test_user"
                assert row["tool_name"] == "complete_task"
                assert row["status"] == "completed"
                assert row["confirmation_required"] is True
            finally:
                await conn.execute("ROLLBACK")
    finally:
        db._pool = original_pool
        await pool.close()


# --- Dashboard audit endpoint tests ---


def test_dashboard_audit_endpoint(client):
    """Verify GET /dashboard/audit returns audit entries with correct shape and 90-day filter."""
    from unittest.mock import MagicMock
    from datetime import datetime, timezone

    mock_rows = [
        {
            "id": 1,
            "created_at": datetime.now(timezone.utc),
            "user_name": "Ruben",
            "tool_name": "add_task",
            "action_summary": "Added task 'Buy milk' for Ruben",
            "status": "completed",
            "confirmation_required": False,
        }
    ]
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = mock_rows
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        resp = client.get("/dashboard/audit?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "audit" in data
        assert len(data["audit"]) == 1
        entry = data["audit"][0]
        assert entry["id"] == 1
        assert entry["user_name"] == "Ruben"
        assert entry["tool_name"] == "add_task"
        assert entry["status"] == "completed"
        assert entry["confirmation_required"] is False
        assert "timestamp" in entry
        assert "action_summary" in entry

    # Verify the SQL contains the 90-day filter
    call_args = mock_conn.fetch.call_args[0]
    assert "interval '90 days'" in call_args[0]


def test_dashboard_audit_empty(client):
    """Verify GET /dashboard/audit returns empty list when no audit rows exist."""
    from unittest.mock import MagicMock

    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = []
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        resp = client.get("/dashboard/audit")
        assert resp.status_code == 200
        assert resp.json() == {"audit": []}


# --- Agent recording tests ---


def _make_tool_call(name: str, args: dict) -> dict:
    return {
        "type": "function",
        "id": "call_test",
        "function": {
            "name": name,
            "arguments": json.dumps(args),
        },
    }


@pytest.mark.asyncio
async def test_run_agent_records_audit_on_tool_call():
    """Verify agent records audit when a mutating tool is executed."""
    from app.agent import run_agent
    from app.tools.base import tool, TOOLS
    import json

    mock_turn1 = {"role": "assistant", "content": None, "tool_calls": [_make_tool_call("add_task", {"title": "Buy milk", "assignee": "Ruben"})]}
    mock_turn2 = {"role": "assistant", "content": "Done!"}

    try:
        # Register a real add_task tool so the agent can call it
        @tool(
            name="add_task",
            description="Add a task.",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "assignee": {"type": "string"},
                },
                "required": ["title"],
            },
        )
        async def add_task_tool(title: str, assignee: str = "") -> str:
            return f"Task '{title}' created for {assignee}"

        from app.llm import ChatResult
        with patch("app.llm.chat", new_callable=AsyncMock) as mock_chat, \
             patch("app.agent.record_tool_call", new_callable=AsyncMock) as mock_record:

            mock_chat.side_effect = [ChatResult(message=mock_turn1), ChatResult(message=mock_turn2)]
            resp = await run_agent("add a task", user="Ruben")

            # Agent should have completed
            assert resp == "Done!"
            # record_tool_call should have been called for add_task
            mock_record.assert_called_once()
            call_kwargs = mock_record.call_args.kwargs
            assert call_kwargs["user_name"] == "Ruben"
            assert call_kwargs["tool_name"] == "add_task"
            assert call_kwargs["status"] == "completed"
            assert "Buy milk" in call_kwargs["action_summary"]
            assert call_kwargs["confirmation_required"] is False

    finally:
        TOOLS.pop("add_task", None)


@pytest.mark.asyncio
async def test_run_agent_records_denied_confirmation():
    """Verify agent records audit with status='denied' when confirmation is rejected."""
    from app.agent import run_agent
    from app.tools.base import tool, TOOLS
    import json

    # User message does NOT contain confirmation words
    mock_turn = {"role": "assistant", "content": None, "tool_calls": [_make_tool_call("create_event", {"title": "Meeting", "start": "2026-07-12T10:00", "end": "2026-07-12T11:00"})]}

    try:
        # Register create_event tool
        @tool(
            name="create_event",
            description="Create a calendar event.",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                },
                "required": ["title", "start"],
            },
        )
        async def create_event_tool(title: str, start: str, end: str = "") -> str:
            return f"Event '{title}' created"

        from app.llm import ChatResult
        # First call returns the tool call, no second call since confirmation fails
        with patch("app.llm.chat", new_callable=AsyncMock) as mock_chat, \
             patch("app.agent.record_tool_call", new_callable=AsyncMock) as mock_record:

            mock_chat.return_value = ChatResult(message=mock_turn)

            # Run agent with an empty history and a user message that does NOT confirm
            resp = await run_agent("no, do not do that", user="Meral")

            # Should return a confirmation required message
            assert "[CONFIRMATION_REQUIRED]" in resp

            # record_tool_call should have been called with status="denied"
            mock_record.assert_called_once()
            call_kwargs = mock_record.call_args.kwargs
            assert call_kwargs["user_name"] == "Meral"
            assert call_kwargs["tool_name"] == "create_event"
            assert call_kwargs["status"] == "denied"
            assert call_kwargs["confirmation_required"] is True

    finally:
        TOOLS.pop("create_event", None)
