"""Tests for the write-action audit trail (Phase 36)."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.audit import record_tool_call


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
