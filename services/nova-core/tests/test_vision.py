"""Tests for vision analysis module — analyze_image() via Ollama.

These tests mock the httpx call to Ollama so no real GPU/vision model is needed.
"""
from __future__ import annotations

import json
import pytest

from unittest.mock import AsyncMock, MagicMock, patch


def _make_ollama_response(content: str) -> dict:
    """Build a mock Ollama /api/chat response dict."""
    return {
        "message": {
            "content": content,
        }
    }


# ---------------------------------------------------------------------------
# Basic JSON parsing and shape validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_image_returns_structured_dict():
    """analyze_image returns dict with summary, events, tasks keys."""
    from app.vision import analyze_image

    mock_ollama_response = _make_ollama_response(
        json.dumps({
            "summary": "School letter about parent-teacher meeting.",
            "events": [{
                "title": "Parent Meeting",
                "start": "2026-09-05T10:00:00",
                "end": "2026-09-05T11:00:00",
                "description": "Annual parent-teacher meeting",
            }],
            "tasks": [{
                "title": "Submit permission slip",
                "assignee": "Ruben",
                "due_at": "2026-08-20",
            }],
        })
    )

    with patch("app.vision.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_ollama_response
        mock_resp.raise_for_status.return_value = None
        mock_client.post.return_value = mock_resp

        result = await analyze_image(b"fake-image-bytes")

        assert result["summary"] == "School letter about parent-teacher meeting."
        assert len(result["events"]) == 1
        assert result["events"][0]["title"] == "Parent Meeting"
        assert result["events"][0]["start"] == "2026-09-05T10:00:00"
        assert result["events"][0]["end"] == "2026-09-05T11:00:00"
        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["title"] == "Submit permission slip"
        assert result["tasks"][0]["assignee"] == "Ruben"
        assert result["tasks"][0]["due_at"] == "2026-08-20"
        assert result["error"] is None


@pytest.mark.asyncio
async def test_analyze_image_empty_events_and_tasks():
    """analyze_image returns empty arrays when document has no events/tasks."""
    from app.vision import analyze_image

    mock_ollama_response = _make_ollama_response(
        json.dumps({
            "summary": "A simple note with no dates or tasks.",
            "events": [],
            "tasks": [],
        })
    )

    with patch("app.vision.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_ollama_response
        mock_resp.raise_for_status.return_value = None
        mock_client.post.return_value = mock_resp

        result = await analyze_image(b"fake-image-bytes")
        assert result["summary"] == "A simple note with no dates or tasks."
        assert result["events"] == []
        assert result["tasks"] == []
        assert result["error"] is None


# ---------------------------------------------------------------------------
# Markdown code fence stripping
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_image_strips_markdown_code_fences():
    """analyze_image handles JSON wrapped in ```json ... ``` fences."""
    from app.vision import analyze_image

    fenced_response = "```json\n" + json.dumps({
        "summary": "Medical appointment reminder.",
        "events": [{
            "title": "Doctor Appointment",
            "start": "2026-09-10T14:30:00",
            "end": "2026-09-10T15:30:00",
            "description": "Annual checkup",
        }],
        "tasks": [],
    }) + "\n```"

    with patch("app.vision.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = _make_ollama_response(fenced_response)
        mock_resp.raise_for_status.return_value = None
        mock_client.post.return_value = mock_resp

        result = await analyze_image(b"fake-image-bytes")
        assert result["events"][0]["title"] == "Doctor Appointment"
        assert result["error"] is None


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_image_ollama_http_error():
    """analyze_image returns error dict on Ollama HTTP error."""
    import httpx
    from app.vision import analyze_image

    with patch("app.vision.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.post.side_effect = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=None,
            response=MagicMock(status_code=500),
        )

        result = await analyze_image(b"fake-image-bytes")
        assert result["summary"] == ""
        assert result["events"] == []
        assert result["tasks"] == []
        assert result["error"] is not None
        assert "HTTP error" in result["error"]


@pytest.mark.asyncio
async def test_analyze_image_ollama_connection_error():
    """analyze_image returns error dict on Ollama connection failure."""
    import httpx
    from app.vision import analyze_image

    with patch("app.vision.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.post.side_effect = httpx.RequestError("Connection refused")

        result = await analyze_image(b"fake-image-bytes")
        assert result["error"] is not None
        assert "Connection error" in result["error"]


@pytest.mark.asyncio
async def test_analyze_image_malformed_json_response():
    """analyze_image returns error dict when Ollama returns non-JSON content."""
    from app.vision import analyze_image

    with patch("app.vision.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = _make_ollama_response("This is not JSON at all")
        mock_resp.raise_for_status.return_value = None
        mock_client.post.return_value = mock_resp

        result = await analyze_image(b"fake-image-bytes")
        assert result["error"] is not None
        assert "JSON parse error" in result["error"]


# ---------------------------------------------------------------------------
# Config-driven model selection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_image_uses_configured_model():
    """analyze_image sends the correct model name in the Ollama payload."""
    from app.vision import analyze_image
    from app.config import settings

    settings.nova_vision_model = "llava:13b"

    with patch("app.vision.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = _make_ollama_response(
            json.dumps({"summary": "Test", "events": [], "tasks": []})
        )
        mock_resp.raise_for_status.return_value = None
        mock_client.post.return_value = mock_resp

        await analyze_image(b"fake-image-bytes")

        # Verify the payload sent to Ollama includes the correct model
        call_kwargs = mock_client.post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["model"] == "llava:13b"
        assert payload["messages"][0]["images"] is not None


@pytest.mark.asyncio
async def test_analyze_image_overrides_model():
    """analyze_image accepts an explicit model override."""
    from app.vision import analyze_image
    from app.config import settings

    settings.nova_vision_model = "llava"

    with patch("app.vision.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = _make_ollama_response(
            json.dumps({"summary": "Test", "events": [], "tasks": []})
        )
        mock_resp.raise_for_status.return_value = None
        mock_client.post.return_value = mock_resp

        await analyze_image(b"fake-image-bytes", model="bakllava")

        call_kwargs = mock_client.post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["model"] == "bakllava"


# ---------------------------------------------------------------------------
# No cloud API check
# ---------------------------------------------------------------------------

def test_analyze_image_no_cloud_imports():
    """vision.py does not import any cloud vision SDK."""
    import app.vision
    import app.vision as vision_module

    source = open(vision_module.__file__).read()
    forbidden = [
        "openai", "google.cloud.vision", "boto3", "rekognition",
        "azure.cognitiveservices.vision",
    ]
    for lib in forbidden:
        assert lib not in source, f"Cloud import {lib} found in vision.py"
