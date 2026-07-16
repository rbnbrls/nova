"""Thin async client for Ollama's chat API (with tool-calling support)."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

from .config import get_active_model_sync, settings

# Kept well below agent.py's whole-turn asyncio.timeout(60) so a slow-but-alive
# Ollama can still be retried at least once within the turn's overall budget.
_REQUEST_TIMEOUT = 120


@dataclass
class ChatResult:
    """Result of a single Ollama /api/chat call (non-streaming).

    Carries the response message dict together with token counts so the
    agent loop can report aggregate token consumption in the trace.
    """
    message: dict
    """The Ollama response message dict (role, content, tool_calls)."""

    prompt_tokens: int = 0
    """Tokens consumed by the prompt (``prompt_eval_count`` in Ollama API)."""

    completion_tokens: int = 0
    """Tokens consumed by the response (``eval_count`` in Ollama API)."""


async def chat(
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    model: str | None = None,
) -> ChatResult:
    """Call Ollama /api/chat once (non-streaming). Returns a ``ChatResult``.

    The result's ``.message`` may contain ``tool_calls``; the agent loop handles those.
    Token counts are extracted from the Ollama response top-level fields.
    """
    payload: dict = {
        "model": model or get_active_model_sync(),
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
                data = resp.json()
                # planner-discipline-allow: prompt_eval_count
                # planner-discipline-allow: eval_count
                return ChatResult(
                    message=data["message"],
                    prompt_tokens=data.get("prompt_eval_count", 0) or 0,
                    completion_tokens=data.get("eval_count", 0) or 0,
                )
        except httpx.HTTPStatusError as exc:
            # Only retry transient server-side failures; a 4xx means retrying
            # the identical request will just fail identically again.
            if exc.response.status_code < 500 or attempt == max_retries - 1:
                raise
            log.warning("Ollama chat attempt %d/%d failed: %s: %s \u2014 retrying in %ds",
                        attempt + 1, max_retries, type(exc).__name__, exc, 2 ** attempt)
            await asyncio.sleep(2 ** attempt)
        except httpx.RequestError as exc:
            if attempt == max_retries - 1:
                raise
            log.warning("Ollama chat attempt %d/%d failed: %s: %s \u2014 retrying in %ds",
                        attempt + 1, max_retries, type(exc).__name__, exc, 2 ** attempt)
            await asyncio.sleep(2 ** attempt)


async def is_ready() -> bool:
    """True if the Ollama server responds (used by /health)."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/version")
            return resp.status_code == 200
    except httpx.HTTPError:
        return False
