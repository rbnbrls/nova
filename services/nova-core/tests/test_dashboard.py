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
    mock_rows = [
        {"title": "Buy milk", "due_at": None, "assignee": "Ruben"},
        {"title": "Clean kitchen", "due_at": None, "assignee": None}
    ]
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = mock_rows
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


def test_dashboard_html_has_mic_button(client):
    """The chat panel includes a voice input mic button with id chat-btn-mic."""
    resp = client.get("/static/index.html")
    assert resp.status_code == 200
    assert b'id="chat-btn-mic"' in resp.content
    # Sanity: chat panel still present
    assert b'id="chat-panel"' in resp.content
