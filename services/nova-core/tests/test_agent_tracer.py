"""Tests for the agent_tracer module — fire-and-forget Postgres trace inserts."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent_tracer import insert_agent_turn, insert_agent_iterations, insert_agent_traces
from app.tracer import AgentTrace


@pytest.fixture
def sample_trace() -> AgentTrace:
    """Build a realistic AgentTrace with iterations for testing."""
    return AgentTrace(
        channel="api",
        user="Ruben",
        latency_ms=1234,
        token_count=567,
        tool_calls=[{"name": "add_task", "status": "completed", "duration_ms": 200}],
        errors=[],
        iteration_count=2,
        got_stuck=False,
        timestamp="2026-07-16T12:00:00Z",
        turn_id="123e4567-e89b-12d3-a456-426614174000",
        iterations=[
            {
                "iteration_num": 1,
                "llm_time_ms": 800,
                "tool_time_ms": 200,
                "tool_name": "add_task",
                "prompt_tokens": 150,
                "completion_tokens": 50,
            },
        ],
    )


def _mock_pool() -> MagicMock:
    """Create a mocked asyncpg pool with a mock connection."""
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    return mock_pool


# ------------------------------------------------------------------
# Test 1: insert_agent_turn executes correct SQL
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insert_agent_turn_calls_execute(sample_trace):
    """insert_agent_turn executes the INSERT with correct parameters."""
    mock_pool = _mock_pool()
    mock_conn = mock_pool.acquire.return_value.__aenter__.return_value

    trace_dict = {
        "turn_id": sample_trace.turn_id,
        "user": sample_trace.user,
        "channel": sample_trace.channel,
        "latency_ms": sample_trace.latency_ms,
        "token_count": sample_trace.token_count,
        "iteration_count": sample_trace.iteration_count,
        "got_stuck": sample_trace.got_stuck,
        "errors": sample_trace.errors,
    }

    with patch("app.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        await insert_agent_turn(trace_dict)

    mock_conn.execute.assert_called_once()
    sql = mock_conn.execute.call_args[0][0]
    assert "INSERT INTO agent_turns" in sql
    assert "$1" in sql


# ------------------------------------------------------------------
# Test 2: insert_agent_iterations executes correct SQL
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insert_agent_iterations_calls_executemany(sample_trace):
    """insert_agent_iterations uses executemany with correct parameters."""
    mock_pool = _mock_pool()
    mock_conn = mock_pool.acquire.return_value.__aenter__.return_value

    with patch("app.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        await insert_agent_iterations(sample_trace.turn_id, sample_trace.iterations)

    mock_conn.executemany.assert_called_once()
    sql = mock_conn.executemany.call_args[0][0]
    assert "INSERT INTO agent_iterations" in sql
    assert "$1" in sql

    # Verify the parameters include the turn_id
    args = mock_conn.executemany.call_args[0][1]
    assert len(args) == 1
    assert args[0][0] == sample_trace.turn_id


# ------------------------------------------------------------------
# Test 3: insert_agent_iterations skips when iterations is empty
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insert_agent_iterations_skips_empty():
    """insert_agent_iterations does nothing when iterations list is empty."""
    mock_pool = _mock_pool()

    with patch("app.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        await insert_agent_iterations("some-turn-id", [])

    # Should not call executemany
    mock_pool.acquire.assert_not_called()


# ------------------------------------------------------------------
# Test 4: insert_agent_traces calls both functions sequentially
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insert_agent_traces_calls_both(sample_trace):
    """insert_agent_traces calls insert_agent_turn then insert_agent_iterations."""
    mock_pool = _mock_pool()

    with patch("app.agent_tracer.insert_agent_turn", new_callable=AsyncMock) as mock_turn, \
         patch("app.agent_tracer.insert_agent_iterations", new_callable=AsyncMock) as mock_iters, \
         patch("app.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        await insert_agent_traces(sample_trace)

    mock_turn.assert_awaited_once()
    mock_iters.assert_awaited_once_with(
        sample_trace.turn_id, sample_trace.iterations
    )


# ------------------------------------------------------------------
# Test 5: DB errors are logged but not raised
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insert_agent_turn_handles_db_error():
    """insert_agent_turn logs warning on DB error and does not raise."""
    trace_dict = {
        "turn_id": "abc",
        "user": "test",
        "channel": "api",
        "latency_ms": 100,
        "token_count": 50,
        "iteration_count": 1,
        "got_stuck": False,
        "errors": [],
    }

    with patch("app.db.get_pool", side_effect=RuntimeError("DB down")):
        try:
            await insert_agent_turn(trace_dict)
        except Exception:
            pytest.fail("insert_agent_turn raised on DB error")


@pytest.mark.asyncio
async def test_insert_agent_iterations_handles_db_error():
    """insert_agent_iterations logs warning on DB error and does not raise."""
    with patch("app.db.get_pool", side_effect=RuntimeError("DB down")):
        try:
            await insert_agent_iterations("abc", [{"iteration_num": 1}])
        except Exception:
            pytest.fail("insert_agent_iterations raised on DB error")
