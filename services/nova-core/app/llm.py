"""Thin async client for Ollama's chat API (with tool-calling support)."""
from __future__ import annotations

import httpx

from .config import settings


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

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{settings.ollama_base_url}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]


async def is_ready() -> bool:
    """True if the Ollama server responds (used by /health)."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/version")
            return resp.status_code == 200
    except httpx.HTTPError:
        return False
