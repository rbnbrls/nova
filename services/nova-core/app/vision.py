"""Vision analysis module — Ollama-based image understanding.

All processing stays on the local GPU via Ollama. No cloud vision APIs are ever
contacted (per D-03).
"""
from __future__ import annotations

import base64
import json
import logging

import httpx

from .config import settings

log = logging.getLogger("nova-core")

_REQUEST_TIMEOUT = 20


async def analyze_image(image_bytes: bytes, model: str | None = None) -> dict:
    """Analyze image bytes via Ollama vision model and return structured extraction.

    Args:
        image_bytes: Raw image bytes (JPEG/PNG — formats WhatsApp sends).
        model: Ollama model tag (defaults to settings.nova_vision_model).

    Returns:
        dict with keys:
            - summary (str): One-paragraph summary of what the photo contains.
            - events (list[dict]): Calendar events found, each with title,
              start, end, description (ISO 8601 strings).
            - tasks (list[dict]): Tasks found, each with title, assignee
              (optional), due_at (optional, ISO date).
            - error (str | None): Error message on failure, None on success.
    """
    chosen = model or settings.nova_vision_model
    base64_str = base64.b64encode(image_bytes).decode("utf-8")

    prompt = (
        "You are analyzing a photo of a document or letter sent to a household assistant. "
        "Extract the following if present:\n"
        "- A one-paragraph summary of what this document/photo contains\n"
        "- Any calendar events mentioned (title, start date/time, end date/time, description)\n"
        "- Any tasks or action items (title, who it's for, due date)\n"
        "Respond in JSON format with keys: summary, events, tasks.\n"
        "events is an array of objects with keys: title, start, end, description\n"
        "tasks is an array of objects with keys: title, assignee, due_at\n"
        "Use ISO 8601 format for dates and datetimes.\n"
        "If no events or tasks are found, return empty arrays."
    )

    payload = {
        "model": chosen,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [base64_str],
            }
        ],
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            resp = await client.post(f"{settings.ollama_base_url}/api/chat", json=payload)
            resp.raise_for_status()
            raw = resp.json()["message"]["content"]
    except httpx.HTTPStatusError as e:
        log.error("Ollama HTTP error on analyze_image: %s", e)
        return {"summary": "", "events": [], "tasks": [], "error": f"HTTP error: {e}"}
    except httpx.RequestError as e:
        log.error("Ollama connection error on analyze_image: %s", e)
        return {"summary": "", "events": [], "tasks": [], "error": f"Connection error: {e}"}
    except (KeyError, ValueError) as e:
        log.error("Ollama unexpected response on analyze_image: %s", e)
        return {"summary": "", "events": [], "tasks": [], "error": f"Unexpected response: {e}"}

    # Try to parse JSON from the response — vision models often wrap JSON in markdown fences
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (possibly with language hint)
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1:]
        # Remove closing fence
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

    try:
        result = json.loads(cleaned)
    except ValueError as e:
        log.error("analyze_image: could not parse JSON from response: %s | raw: %s", e, raw[:500])
        return {"summary": "", "events": [], "tasks": [], "error": f"JSON parse error: {e}"}

    # Normalise the result shape
    return {
        "summary": result.get("summary", ""),
        "events": result.get("events", []),
        "tasks": result.get("tasks", []),
        "error": None,
    }
