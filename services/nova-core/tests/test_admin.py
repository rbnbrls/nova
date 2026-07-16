"""Tests for the Phase 40 admin backend (Plan 01 — read-only SSE status board).

Covers the backend subset of requirements D-02, D-03, D-05, D-08, D-10:
- GET /admin -> 307 redirect to /static/admin.html (D-05)
- GET /admin/stream -> text/event-stream, no auth challenge (D-08, D-10)
- _collect_admin_status runs 5 health checks concurrently with
  asyncio.gather(return_exceptions=True); one failing check does not
  abort the others (D-02)
- _collect_channel_status returns per-user per-channel link state for
  Ruben and Meral (D-03)

Frontend structure tests (test_admin_html_served /
test_admin_html_structure) are added by Plan 02 which creates
admin.html. pytest-asyncio is in auto mode (pyproject.toml) so async
test functions need no @pytest.mark.asyncio decorator.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class DummyStreamingResponse(StreamingResponse):
    """StreamingResponse that yields exactly one item then breaks.

    Mirrors the pattern in test_dashboard.py:67-73 — necessary because
    the real admin SSE generator loops forever (every 45s).
    """

    def __init__(self, content, *args, **kwargs):
        async def wrap_generator(gen):
            async for item in gen:
                yield item
                break

        super().__init__(wrap_generator(content), *args, **kwargs)


def _async_pool_with_conn(mock_conn):
    """Build a MagicMock asyncpg pool whose acquire() returns mock_conn."""
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    mock_pool.acquire.return_value.__aexit__.return_value = None
    return mock_pool


# ---------------------------------------------------------------------------
# Route-level tests — /admin redirect + /admin/stream SSE (D-05, D-08, D-10)
# ---------------------------------------------------------------------------


def test_admin_redirect(client):
    """GET /admin returns 307 to /static/admin.html (D-05)."""
    resp = client.get("/admin", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/static/admin.html"


def test_admin_stream_no_auth(client):
    """GET /admin/stream with no Authorization header returns 200, not 401/403 (D-08)."""
    with patch("app.main._collect_admin_status", new_callable=AsyncMock) as mock_status, \
         patch("app.main.StreamingResponse", new=DummyStreamingResponse):
        mock_status.return_value = {"services": {}, "channels": {}}
        resp = client.get("/admin/stream")
    assert resp.status_code == 200
    assert resp.status_code not in (401, 403)
    # No WWW-Authenticate header should be present
    assert "www-authenticate" not in {k.lower() for k in resp.headers.keys()}


def test_admin_stream_content_type(client):
    """GET /admin/stream returns content-type starting with text/event-stream."""
    with patch("app.main._collect_admin_status", new_callable=AsyncMock) as mock_status, \
         patch("app.main.StreamingResponse", new=DummyStreamingResponse):
        mock_status.return_value = {"services": {}, "channels": {}}
        resp = client.get("/admin/stream")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")


def test_admin_stream_payload_shape(client):
    """First SSE event is `event: status`, second is `data: {...}` with services and channels keys."""
    sample_payload = {
        "services": {
            "ollama": {"status": "ok", "detail": "Model: qwen3:14b", "host": "ollama:11434"},
            "postgres": {"status": "ok", "detail": "5 tables reachable", "host": "postgres:5432"},
            "caldav": {"status": "ok", "detail": "Calendar URL reachable", "host": "radicale:5232"},
            "ha": {"status": "ok", "detail": "HA reachable", "host": "homeassistant:8123"},
            "email": {"status": "ok", "detail": "inbox reachable", "host": "outlook.office365.com:993"},
        },
        "channels": {
            "Ruben": {
                "whatsapp": {"linked": True, "identifier": "+31 6 … 8"},
                "telegram": {"linked": True, "identifier": "Telegram"},
            },
            "Meral": {
                "whatsapp": {"linked": False, "identifier": ""},
                "telegram": {"linked": False, "identifier": ""},
            },
        },
        "models": {"pulling": []},
    }
    with patch("app.main._collect_admin_status", new_callable=AsyncMock) as mock_status, \
         patch("app.main.StreamingResponse", new=DummyStreamingResponse):
        mock_status.return_value = sample_payload
        with client.stream("GET", "/admin/stream") as response:
            assert response.status_code == 200
            iterator = response.iter_lines()
            first_line = next(iterator)
            assert first_line == "event: status"
            second_line = next(iterator)
            assert second_line.startswith("data: ")
            parsed = json.loads(second_line[len("data: "):])
            assert "services" in parsed
            assert "channels" in parsed
            assert "models" in parsed
            assert "pulling" in parsed["models"]
            for svc_name in ("ollama", "postgres", "caldav", "ha", "email"):
                assert svc_name in parsed["services"]
                entry = parsed["services"][svc_name]
                assert "status" in entry
                assert "detail" in entry
                assert "host" in entry
                assert entry["status"] in ("ok", "down")


# ---------------------------------------------------------------------------
# _check_* helper tests — D-02 isolation per-service (privacy: host only)
# ---------------------------------------------------------------------------


async def test_check_ollama():
    """_check_ollama ok branch: returns model.active, model.loading, models."""
    with patch("app.main.llm.is_ready", new_callable=AsyncMock) as mock_ready, \
         patch("app.main.settings") as mock_settings, \
         patch("app.main.admin_models.list_models", new_callable=AsyncMock) as mock_list, \
         patch("app.main.admin_models.get_loading_model") as mock_loading, \
         patch("app.main.get_active_model", new_callable=AsyncMock) as mock_active:
        mock_ready.return_value = True
        mock_settings.nova_model = "qwen3:14b"
        mock_settings.ollama_base_url = "http://localhost:11434"
        mock_list.return_value = [{"name": "qwen3:14b"}]
        mock_loading.return_value = None
        mock_active.return_value = "qwen3:14b"
        from app.main import _check_ollama
        result = await _check_ollama()
    assert result["status"] == "ok"
    assert "qwen3:14b" in result["detail"]
    assert result["host"] == "localhost:11434"
    assert "model" in result
    assert result["model"]["active"] == "qwen3:14b"
    assert result["model"]["loading"] is False
    assert result["model"]["loading_name"] == ""
    assert "models" in result
    assert len(result["models"]) == 1


async def test_check_ollama_down():
    """_check_ollama down branch: is_ready False -> status down, model fields empty."""
    with patch("app.main.llm.is_ready", new_callable=AsyncMock) as mock_ready, \
         patch("app.main.settings") as mock_settings:
        mock_ready.return_value = False
        mock_settings.nova_model = "qwen3:14b"
        mock_settings.ollama_base_url = "http://localhost:11434"
        from app.main import _check_ollama
        result = await _check_ollama()
    assert result["status"] == "down"
    assert result["model"]["active"] == ""
    assert result["model"]["loading"] is False
    assert result["models"] == []


async def test_check_postgres():
    """_check_postgres ok: pool acquirable, fetchval returns count -> status ok, detail mentions tables."""
    mock_conn = AsyncMock()
    mock_conn.execute.return_value = None
    mock_conn.fetchval.return_value = 7
    mock_pool = _async_pool_with_conn(mock_conn)

    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("app.main.settings") as mock_settings:
        mock_get_pool.return_value = mock_pool
        mock_settings.postgres_host = "postgres"
        mock_settings.postgres_port = 5432
        from app.main import _check_postgres
        result = await _check_postgres()
    assert result["status"] == "ok"
    assert "tables" in result["detail"]
    assert result["host"] == "postgres:5432"


async def test_check_imap_not_configured():
    """_check_imap when nova_imap_host is empty / connection None -> down, 'Not configured'."""
    with patch("app.main._get_imap_connection", new_callable=AsyncMock) as mock_imap, \
         patch("app.main.settings") as mock_settings:
        mock_imap.return_value = None
        mock_settings.nova_imap_host = ""
        mock_settings.nova_imap_user = ""
        from app.main import _check_imap
        result = await _check_imap()
    assert result["status"] == "down"
    assert "Not configured" in result["detail"]


# ---------------------------------------------------------------------------
# _collect_admin_status isolation (D-02) — return_exceptions=True proves
# ---------------------------------------------------------------------------


async def test_collect_status_isolation():
    """When one _check_* helper raises, _collect_admin_status still returns 5 services.

    This proves asyncio.gather(return_exceptions=True) is in use — one
    failure does not abort the other 4 checks.
    """
    ok_shape = {"status": "ok", "detail": "fine", "host": "h:1"}
    with patch("app.main._check_caldav", new_callable=AsyncMock) as mcaldav, \
         patch("app.main._check_ollama", new_callable=AsyncMock) as molla, \
         patch("app.main._check_postgres", new_callable=AsyncMock) as mpost, \
         patch("app.main._check_ha", new_callable=AsyncMock) as mha, \
         patch("app.main._check_imap", new_callable=AsyncMock) as mimap, \
         patch("app.main._collect_channel_status", new_callable=AsyncMock) as mchan:
        mcaldav.side_effect = RuntimeError("boom")
        molla.return_value = ok_shape
        mpost.return_value = ok_shape
        mha.return_value = ok_shape
        mimap.return_value = ok_shape
        mchan.return_value = {}
        from app.main import _collect_admin_status
        result = await _collect_admin_status()
    services = result["services"]
    # All 5 must be present (the isolate predicate)
    assert set(services.keys()) == {"ollama", "postgres", "caldav", "ha", "email"}
    # The raised one must be reported as down — not propagated
    assert services["caldav"]["status"] == "down"
    # The others must still be reported ok
    assert services["ollama"]["status"] == "ok"
    assert services["postgres"]["status"] == "ok"
    assert services["ha"]["status"] == "ok"
    assert services["email"]["status"] == "ok"


# ---------------------------------------------------------------------------
# _collect_channel_status (D-03) — per-user per-channel link state
# ---------------------------------------------------------------------------


async def test_collect_channel_status():
    """_collect_channel_status shapes rows into per-user {whatsapp, telegram} link dicts (D-03)."""
    rows = [
        {"name": "Ruben", "whatsapp_number": "+31612345678",
         "telegram_chat_id": "12345", "channels_enabled": ["whatsapp", "telegram"]},
        {"name": "Meral", "whatsapp_number": None,
         "telegram_chat_id": None, "channels_enabled": []},
    ]
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = rows
    mock_pool = _async_pool_with_conn(mock_conn)

    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        from app.main import _collect_channel_status
        result = await _collect_channel_status()
    # Ruben: linked both channels, identifier masked
    assert result["Ruben"]["whatsapp"]["linked"] is True
    assert "+31 6 12" in result["Ruben"]["whatsapp"]["identifier"]
    assert result["Ruben"]["telegram"]["linked"] is True
    # Meral: nothing linked
    assert result["Meral"]["whatsapp"]["linked"] is False
    assert result["Meral"]["telegram"]["linked"] is False


# ---------------------------------------------------------------------------
# Frontend structure tests — Plan 02 (added when admin.html was created)
# ---------------------------------------------------------------------------


def test_admin_html_served(client):
    """GET /static/admin.html returns 200."""
    resp = client.get("/static/admin.html")
    assert resp.status_code == 200


def test_admin_html_structure(client):
    """admin.html contains expected structural elements."""
    resp = client.get("/static/admin.html")
    content = resp.content
    assert b'id="system-status-panel"' in content
    assert b'id="channel-status-panel"' in content
    assert b'id="service-ollama"' in content
    assert b'id="service-postgres"' in content
    assert b'id="service-caldav"' in content
    assert b'id="service-ha"' in content
    assert b'id="service-email"' in content
    assert b'id="channel-ruben-whatsapp"' in content
    assert b'id="channel-meral-whatsapp"' in content
    assert b'href="/"' in content
    assert b'src="/static/admin.js"' in content


def test_admin_html_no_admin_link_on_dashboard(client):
    """GET /static/index.html does not contain any /admin reference (D-07)."""
    resp = client.get("/static/index.html")
    assert b"/admin" not in resp.content