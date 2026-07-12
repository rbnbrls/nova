"""Agent-run tracing: fire-and-forget structured traces to OpenObserve.

Every agent turn (success, stuck, error) emits a structured JSON trace with
the fields required by D-01.  The emission is fire-and-forget — it never blocks
the agent response and never raises if OpenObserve is down.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

import httpx

log = logging.getLogger("nova-core.tracer")


@dataclass
class AgentTrace:
    """Structured payload for a single agent-turn trace.

    All fields are set by the agent loop before calling ``emit_trace``.
    """

    channel: str
    """WhatsApp / telegram / api / voice"""

    user: str
    """Household name — the *target user* of the turn."""

    latency_ms: int
    """Wall-clock milliseconds of the entire ``run_agent`` call."""

    token_count: int
    """Total tokens consumed (prompt + eval) across all LLM calls in this turn."""

    tool_calls: list[dict] = field(default_factory=list)
    """Each entry: ``{"name": str, "status": str, "duration_ms": int}``.

    ``status`` is one of ``"completed"``, ``"denied"``, or ``"error"``.
    """

    errors: list[dict] = field(default_factory=list)
    """Each entry: ``{"tool": str, "error": str}`` — error message truncated to 500 chars."""

    iteration_count: int = 0
    """Number of LLM-tool round trips in this turn (1-based)."""

    got_stuck: bool = False
    """``True`` when the agent hit ``nova_max_iterations`` without producing a final answer."""

    timestamp: str = ""
    """ISO-8601 UTC timestamp (set at trace-creation time)."""


async def emit_trace(trace: AgentTrace) -> None:
    """Fire-and-forget POST of *trace* to the OpenObserve ``agent_traces`` stream.

    Reads credentials from environment variables (same pattern as
    ``log_anomaly._query_openobserve``).  If ``OPENOBSERVE_URL`` is empty/falsy
    the call is silently skipped.  All ``httpx`` exceptions are caught and
    logged at warning level — the caller is never blocked or raised through.
    """
    base_url = os.environ.get("OPENOBSERVE_URL", "").rstrip("/")
    if not base_url:
        log.debug("OPENOBSERVE_URL not set — skipping trace emission")
        return

    org = os.environ.get("OPENOBSERVE_ORG", "default")
    user = os.environ.get("OPENOBSERVE_USER", "")
    password = os.environ.get("OPENOBSERVE_PASSWORD", "")

    url = f"{base_url}/api/{org}/agent_traces/_json"
    payload = asdict(trace)

    auth = (user, password) if user and password else None

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(url, json=payload, auth=auth)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("emit_trace: OpenObserve POST failed — %s", exc)
    except Exception as exc:
        log.warning("emit_trace: unexpected error — %s", exc)
