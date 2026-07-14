"""Ollama model management — proxy wrappers around the Ollama REST API.

Provides lifecycle operations (list, pull, delete, load) together with
thread-safe pull-progress tracking for the admin panel.

This module is pure Ollama API proxying + pull state tracking — it does NOT
define any FastAPI endpoint routes (those belong in main.py).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field

import httpx

from .config import settings

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PULL_TIMEOUT = 600  # 10 minutes — large model downloads are slow
_MODEL_NAME_RE = re.compile(r"^[a-zA-Z0-9:_\-./]+$")


# ---------------------------------------------------------------------------
# Pull-task tracking (module-level, thread-safe via asyncio.Lock)
# ---------------------------------------------------------------------------


@dataclass
class PullTask:
    """Represents a single model-pull operation tracked in ``_pull_tasks``.

    Status transitions: pending → downloading → extracting → done | error
    """

    model: str
    status: str = "pending"
    progress: float = 0.0
    message: str = ""
    error: str | None = None


_pull_tasks: dict[str, PullTask] = {}
_pull_lock = asyncio.Lock()
_model_loading: dict[str, str | None] = {"model": None}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_model_name(name: str) -> bool:
    """Return True if *name* matches the allowed model-name pattern."""
    return bool(_MODEL_NAME_RE.match(name))


# ---------------------------------------------------------------------------
# Model listing
# ---------------------------------------------------------------------------


async def list_models() -> list[dict]:
    """List all models available in the local Ollama registry.

    Returns ``[]`` on any connection or HTTP error (safe for admin display).
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return data.get("models", [])
    except httpx.HTTPError:
        log.warning("Failed to list models from Ollama")
        return []


# ---------------------------------------------------------------------------
# Model deletion
# ---------------------------------------------------------------------------


async def delete_model(model: str) -> dict:
    """Delete a model from the local Ollama registry.

    Returns ``{"status": "deleted"}`` on success.
    Returns ``{"status": "error", "detail": ...}`` with a safe message on 404.
    Re-raises on other HTTP/connection errors (caller handles logging).
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                "DELETE",
                f"{settings.ollama_base_url}/api/delete",
                json={"model": model},
            )
            if resp.status_code == 404:
                return {"status": "error", "detail": f"Model '{model}' not found"}
            resp.raise_for_status()
            return {"status": "deleted"}
    except httpx.HTTPStatusError as exc:
        log.warning("Failed to delete model %s: %s", model, exc)
        return {"status": "error", "detail": "Failed to delete model"}
    except httpx.RequestError as exc:
        log.warning("Connection error deleting model %s: %s", model, exc)
        return {"status": "error", "detail": "Cannot reach Ollama"}


# ---------------------------------------------------------------------------
# Model pull (streaming, with progress tracking)
# ---------------------------------------------------------------------------


async def pull_model(model: str) -> None:
    """Start a background pull of *model* from the Ollama registry.

    This function acquires ``_pull_lock`` to enforce **one concurrent pull**
    at a time.  If a pull is already in progress, the caller is responsible
    for detecting the duplicate (the lock will block, then the function is
    a no-op if the model is already being pulled).

    Progress is streamed via Ollama's ndjson response lines and written into
    the module-level ``_pull_tasks`` dict.
    """
    async with _pull_lock:
        if model in _pull_tasks and _pull_tasks[model].status not in ("done", "error"):
            log.info("Pull already in progress for %s — skipping", model)
            return

        _pull_tasks[model] = PullTask(model=model, status="pending")

    try:
        async with httpx.AsyncClient(timeout=_PULL_TIMEOUT) as client:
            async with client.stream(
                "POST",
                f"{settings.ollama_base_url}/api/pull",
                json={"model": model, "stream": True},
            ) as response:
                response.raise_for_status()
                async with _pull_lock:
                    task = _pull_tasks.get(model)
                    if task:
                        task.status = "downloading"

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if "error" in data:
                        async with _pull_lock:
                            t = _pull_tasks.get(model)
                            if t:
                                t.status = "error"
                                t.error = data["error"]
                        return

                    status = data.get("status", "")
                    async with _pull_lock:
                        t = _pull_tasks.get(model)
                        if not t:
                            continue

                        if status == "pulling manifest":
                            t.status = "downloading"
                            t.message = "Pulling manifest…"
                        elif status.startswith("pulling "):
                            t.status = "downloading"
                            # Progress: "pulling sha256:abc...  xx%"
                            completed = data.get("completed", 0)
                            total = data.get("total", 0)
                            if total:
                                t.progress = completed / total
                            t.message = status
                        elif status == "verifying sha256 digest":
                            t.status = "extracting"
                            t.message = "Verifying…"
                            t.progress = 0.0
                        elif status == "success":
                            t.status = "done"
                            t.progress = 1.0
                            t.message = "Done"
                        else:
                            t.message = status

        # Ensure terminal state if stream ended without explicit "success"
        async with _pull_lock:
            t = _pull_tasks.get(model)
            if t and t.status == "downloading":
                t.status = "done"
                t.progress = 1.0
                t.message = "Done"

    except httpx.HTTPError as exc:
        async with _pull_lock:
            t = _pull_tasks.get(model)
            if t:
                t.status = "error"
                t.error = str(exc)
    except asyncio.TimeoutError:
        async with _pull_lock:
            t = _pull_tasks.get(model)
            if t:
                t.status = "error"
                t.error = "Pull timed out after 10 minutes"


async def get_pull_status(model: str) -> PullTask | None:
    """Return the current ``PullTask`` for *model*, or ``None``."""
    async with _pull_lock:
        return _pull_tasks.get(model)


async def clear_pull_state(model: str) -> None:
    """Remove the pull-tracking entry for *model*."""
    async with _pull_lock:
        _pull_tasks.pop(model, None)


async def get_all_pull_tasks() -> list[PullTask]:
    """Return a snapshot of all tracked pull tasks (used by SSE generator)."""
    async with _pull_lock:
        return list(_pull_tasks.values())


# ---------------------------------------------------------------------------
# Model loading / unloading
# ---------------------------------------------------------------------------


async def load_model(model: str, keep_alive: str = "5m") -> bool:
    """Send a generate request to Ollama to load *model* into GPU memory.

    Returns ``True`` on success, ``False`` if the request failed (Ollama
    unresponsive, model not found, etc.).
    """
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={"model": model, "keep_alive": keep_alive},
            )
            return resp.status_code == 200
    except httpx.HTTPError:
        log.warning("Failed to load model %s", model)
        return False


# ---------------------------------------------------------------------------
# Loading-state helpers (for main.py endpoint coordination)
# ---------------------------------------------------------------------------


def set_loading_model(model: str | None) -> None:
    """Set the model currently being loaded (sync, endpoint-coordination)."""
    _model_loading["model"] = model


def get_loading_model() -> str | None:
    """Return the model currently being loaded, or ``None``."""
    return _model_loading.get("model")
