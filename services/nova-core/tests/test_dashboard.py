import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_dashboard_redirect(client):
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/static/index.html"


def test_dashboard_tasks_query(client):
    # Mock database pool and connection
    from uuid import UUID
    mock_task_rows = [
        {"id": UUID("00000000-0000-0000-0000-000000000001"), "title": "Buy milk", "due_at": None, "priority": "medium", "planning_state": None, "labels": [], "is_template": False, "template_id": None, "created_at": None, "assignee": "Ruben"},
        {"id": UUID("00000000-0000-0000-0000-000000000002"), "title": "Clean kitchen", "due_at": None, "priority": "medium", "planning_state": None, "labels": [], "is_template": False, "template_id": None, "created_at": None, "assignee": None}
    ]
    mock_conn = AsyncMock()
    mock_conn.fetch.side_effect = [mock_task_rows, [], []]
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        resp = client.get("/dashboard/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data
        assert len(data["tasks"]) == 2
        assert data["tasks"][0]["title"] == "Buy milk"
        assert data["tasks"][0]["assignee"] == "Ruben"
        assert data["tasks"][1]["assignee"] == "unassigned"


def test_dashboard_events_query(client):
    # Mock CalDAV calendar events
    mock_calendar = MagicMock()
    mock_calendar.search.return_value = []
    
    with patch("app.main.settings") as mock_settings, \
         patch("app.main._get_calendar") as mock_get_cal:
         
        mock_settings.nova_timezone = "Europe/Amsterdam"
        mock_get_cal.return_value = mock_calendar
        
        resp = client.get("/dashboard/events")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert isinstance(data["events"], list)


def test_dashboard_stream_sse(client):
    # Mock tasks, events, and audit data
    mock_tasks = {"tasks": [{"title": "Clean room", "due_at": None, "assignee": "Ruben"}]}
    mock_events = {"events": []}
    mock_audit = {"audit": []}
    
    from fastapi.responses import StreamingResponse
    
    class DummyStreamingResponse(StreamingResponse):
        def __init__(self, content, *args, **kwargs):
            async def wrap_generator(gen):
                async for item in gen:
                    yield item
                    break
            super().__init__(wrap_generator(content), *args, **kwargs)
            
    with patch("app.main.dashboard_tasks", new_callable=AsyncMock) as mock_tasks_call, \
         patch("app.main.dashboard_events", new_callable=AsyncMock) as mock_events_call, \
         patch("app.main.dashboard_audit", new_callable=AsyncMock) as mock_audit_call, \
         patch("app.main.StreamingResponse", new=DummyStreamingResponse):
         
        mock_tasks_call.return_value = mock_tasks
        mock_events_call.return_value = mock_events
        mock_audit_call.return_value = mock_audit
        
        # We can read the first line of the stream response to verify EventStream format
        with client.stream("GET", "/dashboard/stream") as response:
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
            
            # Read first line
            iterator = response.iter_lines()
            first_line = next(iterator)
            
            # Verify parsed JSON structure
            import json
            raw_json = first_line[len("data: "):]
            parsed = json.loads(raw_json)
            assert "tasks" in parsed
            assert "events" in parsed
            assert parsed["tasks"][0]["title"] == "Clean room"


def test_dashboard_chat_returns_reply(client):
    """POST /dashboard/chat with valid message returns {reply} with 200."""
    with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = "I can help with that!"
        resp = client.post("/dashboard/chat", json={"user": "Ruben", "message": "What's on my agenda?"})
        assert resp.status_code == 200
        assert resp.json()["reply"] == "I can help with that!"
        mock_run.assert_awaited_once_with("What's on my agenda?", user="Ruben", history=None, channel="dashboard")


def test_dashboard_chat_empty_message(client):
    """POST /dashboard/chat with empty message returns 400."""
    resp = client.post("/dashboard/chat", json={"user": "Ruben", "message": ""})
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()


def test_dashboard_chat_agent_error(client):
    """POST /dashboard/chat when run_agent raises returns 502."""
    with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = RuntimeError("LLM crashed")
        resp = client.post("/dashboard/chat", json={"user": "Ruben", "message": "Hello"})
        assert resp.status_code == 502
        assert "trouble" in resp.json()["detail"].lower()


def test_dashboard_html_has_chat_panel(client):
    """The static index.html page includes the chat-panel section."""
    resp = client.get("/static/index.html")
    assert resp.status_code == 200
    assert b'class="dashboard-card glass-panel chat-panel"' in resp.content or b'id="chat-panel"' in resp.content


def test_dashboard_task_detail_endpoint(client):
    """GET /dashboard/task/{id} returns full task detail."""
    from datetime import datetime
    mock_row = {
        "id": "00000000-0000-0000-0000-000000000001",
        "title": "Buy milk",
        "due_at": datetime(2026, 7, 15, 16, 0, 0),
        "priority": "high",
        "status": "active",
        "assignee": "Ruben",
        "created_by": "Ruben",
        "labels": ["groceries"],
        "is_template": False,
        "template_id": None,
        "planning_state": "in_progress",
        "task_duration_min": 15,
        "earliest_start": None,
        "latest_end": None,
        "hard_deadline": None,
        "soft_deadline": None,
        "created_at": datetime(2026, 7, 14),
    }
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = mock_row
    mock_conn.fetch.side_effect = [[], [], []]  # notes, blockers, dependents
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        resp = client.get("/dashboard/task/00000000-0000-0000-0000-000000000001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Buy milk"
        assert data["assignee"] == "Ruben"
        assert data["priority"] == "high"
        assert "labels" in data
        assert "notes" in data
        assert "blockers" in data


def test_dashboard_task_detail_not_found(client):
    """GET /dashboard/task/{id} returns 404 when task not found."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = None
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        resp = client.get("/dashboard/task/00000000-0000-0000-0000-000000009999")
        assert resp.status_code == 404


def test_dashboard_tasks_response_includes_new_fields(client):
    """GET /dashboard/tasks now includes enriched fields."""
    mock_rows = [
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "title": "Buy milk",
            "due_at": None,
            "priority": "high",
            "planning_state": None,
            "labels": ["groceries"],
            "is_template": False,
            "template_id": None,
            "created_at": None,
            "assignee": "Ruben",
        },
    ]
    mock_conn = AsyncMock()
    mock_conn.fetch.side_effect = [mock_rows, [], []]  # tasks, note counts, blockers
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        resp = client.get("/dashboard/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data
        task = data["tasks"][0]
        assert "id" in task
        assert "labels" in task
        assert "is_template" in task
        assert "note_count" in task
        assert "blocked_by" in task
        assert "planning_state" in task


def test_dashboard_html_has_mic_button(client):
    """The chat panel includes a voice input mic button with id chat-btn-mic."""
    resp = client.get("/static/index.html")
    assert resp.status_code == 200
    assert b'id="chat-btn-mic"' in resp.content
    # Sanity: chat panel still present
    assert b'id="chat-panel"' in resp.content


# ------------------------------------------------------------------
# Traces endpoint tests
# ------------------------------------------------------------------


def test_dashboard_traces_endpoint(client):
    """GET /dashboard/traces returns traces with iterations."""
    from datetime import datetime

    mock_turn_row = {
        "id": "00000000-0000-0000-0000-000000000001",
        "user": "Ruben",
        "channel": "api",
        "total_latency_ms": 1234,
        "token_count": 567,
        "iteration_count": 2,
        "got_stuck": False,
        "error_count": 0,
        "created_at": datetime(2026, 7, 16, 12, 0, 0),
    }
    mock_iteration_row = {
        "turn_id": "00000000-0000-0000-0000-000000000001",
        "iteration_num": 1,
        "llm_time_ms": 800,
        "tool_time_ms": 200,
        "tool_name": "add_task",
        "prompt_tokens": 150,
        "completion_tokens": 50,
    }
    mock_conn = AsyncMock()
    mock_conn.fetch.side_effect = [
        [mock_turn_row],        # First fetch: agent_turns query
        [mock_iteration_row],   # Second fetch: agent_iterations query
    ]
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        resp = client.get("/dashboard/traces")

    assert resp.status_code == 200
    data = resp.json()
    assert "traces" in data
    assert len(data["traces"]) == 1
    trace = data["traces"][0]
    assert trace["user"] == "Ruben"
    assert trace["channel"] == "api"
    assert trace["total_latency_ms"] == 1234
    assert trace["token_count"] == 567
    assert trace["iteration_count"] == 2
    assert trace["got_stuck"] is False
    assert trace["error_count"] == 0
    assert "created_at" in trace
    assert len(trace["iterations"]) == 1
    assert trace["iterations"][0]["iteration_num"] == 1


def test_dashboard_traces_filters_by_user(client):
    """GET /dashboard/traces with user param filters correctly."""
    from datetime import datetime

    mock_turn_row = {
        "id": "00000000-0000-0000-0000-000000000002",
        "user": "Meral",
        "channel": "api",
        "total_latency_ms": 500,
        "token_count": 100,
        "iteration_count": 1,
        "got_stuck": False,
        "error_count": 0,
        "created_at": datetime(2026, 7, 16, 13, 0, 0),
    }
    mock_conn = AsyncMock()
    mock_conn.fetch.side_effect = [
        [mock_turn_row],   # First fetch: agent_turns filtered by user
        [],                 # Second fetch: no iterations
    ]
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        resp = client.get("/dashboard/traces?user=Meral")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["traces"]) == 1
    assert data["traces"][0]["user"] == "Meral"


def test_dashboard_traces_empty(client):
    """GET /dashboard/traces returns empty list when no traces exist."""
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = []  # No turns
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        resp = client.get("/dashboard/traces")

    assert resp.status_code == 200
    data = resp.json()
    assert data == {"traces": []}
