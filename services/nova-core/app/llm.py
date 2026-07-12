"""Thin async client for Ollama's chat API (with tool-calling support)."""
from __future__ import annotations

import asyncio
import logging

import httpx

log = logging.getLogger(__name__)

from .config import settings

# Kept well below agent.py's whole-turn asyncio.timeout(60) so a slow-but-alive
# Ollama can still be retried at least once within the turn's overall budget.
_REQUEST_TIMEOUT = 20


async def chat(
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    model: str | None = None,
) -> dict:
    """Call Ollama /api/chat once (non-streaming). Returns the `message` object.

    The returned message may contain `tool_calls`; the agent loop handles those.
    """
    payload: dict = {
        "model": model or settings.nova_model,
        "messages": messages,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools

    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                resp = await client.post(f"{settings.ollama_base_url}/api/chat", json=payload)
                resp.raise_for_status()
                return resp.json()["message"]
        except httpx.HTTPStatusError as exc:
            # Only retry transient server-side failures; a 4xx means retrying
            # the identical request will just fail identically again.
            if exc.response.status_code < 500 or attempt == max_retries - 1:
                raise
            log.warning("Ollama chat attempt %d/%d failed: %s \u2014 retrying in %ds",
                        attempt + 1, max_retries, exc, 2 ** attempt)
            await asyncio.sleep(2 ** attempt)
        except httpx.RequestError as exc:
            if attempt == max_retries - 1:
                raise
            log.warning("Ollama chat attempt %d/%d failed: %s \u2014 retrying in %ds",
                        attempt + 1, max_retries, exc, 2 ** attempt)
            await asyncio.sleep(2 ** attempt)


async def is_ready() -> bool:
    """True if the Ollama server responds (used by /health)."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/version")
            return resp.status_code == 200
    except httpx.HTTPError:
        return False
