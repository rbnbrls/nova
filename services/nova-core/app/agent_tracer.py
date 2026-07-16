"""Fire-and-forget Postgres writer for agent turn + iteration traces.

After each agent turn completes, ``insert_agent_traces()`` is called via
``asyncio.create_task()`` to write the normalized trace data into the
``agent_turns`` and ``agent_iterations`` tables.  All DB write errors are
logged at warning level and silently absorbed — the caller is never blocked
or raised through.

Per D-03: traces go to BOTH OpenObserve (via ``tracer.emit_trace``) AND
Postgres (via this module).  Per D-09: the schema is normalized with
FK-linked ``agent_turns`` and ``agent_iterations`` tables.
"""
from __future__ import annotations

import logging

from .tracer import AgentTrace

log = logging.getLogger("nova-core.agent_tracer")


async def insert_agent_turn(trace: dict) -> None:
    """Insert a single agent-turn record into the ``agent_turns`` table.

    Fire-and-forget — expected to be called via ``asyncio.create_task()``.
    Returns ``None`` on success, logs warning on failure (never raises).
    """
    try:
        from . import db

        pool = await db.get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_turns (
                    id, user, channel, total_latency_ms, token_count,
                    iteration_count, got_stuck, error_count
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (id) DO NOTHING
                """,
                trace.get("turn_id"),
                trace.get("user", ""),
                trace.get("channel", ""),
                trace.get("latency_ms", 0),
                trace.get("token_count", 0),
                trace.get("iteration_count", 0),
                trace.get("got_stuck", False),
                len(trace.get("errors", [])),
            )
    except Exception as exc:
        log.warning("insert_agent_turn failed for turn %s: %s",
                     trace.get("turn_id", "?"), exc)


async def insert_agent_iterations(turn_id: str, iterations: list[dict]) -> None:
    """Insert per-iteration records into the ``agent_iterations`` table.

    Uses ``executemany`` for a single batched insert.  Returns ``None``,
    logs warning on failure (never raises).
    """
    if not iterations:
        return

    try:
        from . import db

        pool = await db.get_pool()
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO agent_iterations (
                    turn_id, iteration_num, llm_time_ms, tool_time_ms,
                    tool_name, prompt_tokens, completion_tokens
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                [
                    (
                        turn_id,
                        it.get("iteration_num", 0),
                        it.get("llm_time_ms", 0),
                        it.get("tool_time_ms", 0),
                        it.get("tool_name", ""),
                        it.get("prompt_tokens", 0),
                        it.get("completion_tokens", 0),
                    )
                    for it in iterations
                ],
            )
    except Exception as exc:
        log.warning("insert_agent_iterations failed for turn %s: %s",
                     turn_id, exc)


async def insert_agent_traces(trace: AgentTrace) -> None:
    """Convenience wrapper: insert turn + iterations in sequence.

    Both operations run inside a single connection (not a transaction — if
    iterations fail, the turn still persists).  Turn must exist before
    iterations (FK constraint).
    """
    trace_dict = _trace_to_dict(trace)
    await insert_agent_turn(trace_dict)
    if trace.iterations and trace.turn_id:
        await insert_agent_iterations(trace.turn_id, trace.iterations)


def _trace_to_dict(trace: AgentTrace) -> dict:
    """Convert an ``AgentTrace`` to a plain dict for Postgres insertion."""
    return {
        "turn_id": trace.turn_id,
        "user": trace.user,
        "channel": trace.channel,
        "latency_ms": trace.latency_ms,
        "token_count": trace.token_count,
        "iteration_count": trace.iteration_count,
        "got_stuck": trace.got_stuck,
        "errors": trace.errors,
    }
