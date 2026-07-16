"""Shared async progress-event bus for the dashboard SSE stream.

The agent loop pushes ephemeral step-namespace progress events into a bounded
:class:`asyncio.Queue`; the ``/dashboard/stream`` SSE generator drains the
queue and yields named ``progress`` events between its regular poll cycles.

The queue is process-local and bounded (maxsize=100) — progress events are
ephemeral by nature and losing one under high load is acceptable.
"""
from __future__ import annotations

import asyncio
import logging


log = logging.getLogger("nova-core.progress")

_progress_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)
"""Bounded queue shared between the agent loop (writer) and SSE endpoint (reader)."""


async def push_progress(step: str, elapsed_s: float) -> None:
    """Push a progress event to the dashboard SSE stream (non-blocking).

    Silently drops the event when the queue is full — progress events are
    ephemeral and losing one under high load is acceptable.

    Args:
        step: Name of the current step (e.g. ``"llm"``, ``"complete_task"``).
        elapsed_s: Wall-clock seconds elapsed for this step so far.
    """
    try:
        _progress_queue.put_nowait({"step": step, "elapsed_s": elapsed_s})
    except asyncio.QueueFull:
        log.warning("progress queue full, dropping event: step=%s", step)


def get_progress_queue() -> asyncio.Queue[dict]:
    """Return the shared progress queue — used by the SSE generator to drain events.

    Returns the same module-level ``_progress_queue`` instance.  Callers
    should never access the private module attribute directly.
    """
    return _progress_queue
