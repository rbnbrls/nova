"""Unit tests for ForgejoClient.

Follows the project's existing test patterns — uses AsyncMock for httpx
client, MagicMock for response objects, and patches at the class level.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.forgejo import ForgejoClient, ForgejoError


@pytest.fixture
def client() -> ForgejoClient:
    return ForgejoClient(
        base_url="https://git.example.com",
        repo="test/nova",
        token="test-token",
    )


def _make_mock_async_client(
    response: MagicMock | None = None,
    side_effect: list[MagicMock] | None = None,
) -> AsyncMock:
    """Build an AsyncMock that behaves like an async context manager.

    ``async with AsyncClient() as client:`` calls ``__aenter__`` on the
    returned instance.  We wire it so that ``__aenter__`` returns an
    ``AsyncMock`` whose ``request`` method yields the given response(s).
    """
    inner = AsyncMock()
    if side_effect:
        inner.request.side_effect = side_effect
    elif response is not None:
        inner.request.return_value = response

    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=inner)
    ctx_mgr.__aexit__ = AsyncMock(return_value=None)
    return ctx_mgr


def _make_mock_resp(status_code: int = 200, json_data: object = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = "{}"
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


# ------------------------------------------------------------------
# test_create_issue
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_issue(client: ForgejoClient):
    """Mock POST /api/v1/repos/.../issues returns {"number": 42}."""
    mock_resp = _make_mock_resp(201, {"number": 42})
    ctx_mgr = _make_mock_async_client(response=mock_resp)

    with patch("httpx.AsyncClient", return_value=ctx_mgr):
        number = await client.create_issue("Test Issue", "Test body")

    assert number == 42
    inner = ctx_mgr.__aenter__.return_value
    inner.request.assert_called_once()
    _, kwargs = inner.request.call_args
    assert kwargs["json"]["title"] == "Test Issue"
    assert kwargs["json"]["body"] == "Test body"
    assert "labels" not in kwargs["json"]


# ------------------------------------------------------------------
# test_create_issue_with_labels
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_issue_with_labels(client: ForgejoClient):
    """Mock GET /labels to resolve label IDs, mock POST /issues with resolved IDs."""
    labels_resp = _make_mock_resp(200, [
        {"id": 1, "name": "bug"},
        {"id": 2, "name": "monitoring"},
    ])
    issue_resp = _make_mock_resp(201, {"number": 99})

    ctx_mgr = _make_mock_async_client(side_effect=[labels_resp, issue_resp])

    with patch("httpx.AsyncClient", return_value=ctx_mgr):
        number = await client.create_issue("Bug report", "Details", labels=["bug", "monitoring"])

    assert number == 99
    inner = ctx_mgr.__aenter__.return_value
    assert inner.request.call_count == 2
    first_call = inner.request.call_args_list[0]
    assert first_call[0][0] == "GET"
    assert "labels" in first_call[0][1]

    second_call = inner.request.call_args_list[1]
    assert second_call[0][0] == "POST"
    assert second_call[1]["json"]["labels"] == [1, 2]


# ------------------------------------------------------------------
# test_comment_issue
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_comment_issue(client: ForgejoClient):
    """Mock POST /issues/{n}/comments — assert call succeeds."""
    mock_resp = _make_mock_resp(201)
    ctx_mgr = _make_mock_async_client(response=mock_resp)

    with patch("httpx.AsyncClient", return_value=ctx_mgr):
        await client.comment_issue(42, "A comment")

    inner = ctx_mgr.__aenter__.return_value
    inner.request.assert_called_once()
    _, kwargs = inner.request.call_args
    assert kwargs["json"]["body"] == "A comment"


# ------------------------------------------------------------------
# test_close_issue
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_issue(client: ForgejoClient):
    """Mock PATCH /issues/{n} with state=closed — assert call succeeds."""
    mock_resp = _make_mock_resp(200)
    ctx_mgr = _make_mock_async_client(response=mock_resp)

    with patch("httpx.AsyncClient", return_value=ctx_mgr):
        await client.close_issue(42)

    inner = ctx_mgr.__aenter__.return_value
    inner.request.assert_called_once()
    _, kwargs = inner.request.call_args
    assert kwargs["json"]["state"] == "closed"


# ------------------------------------------------------------------
# test_add_label
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_label(client: ForgejoClient):
    """Mock POST /issues/{n}/labels — assert call succeeds."""
    labels_resp = _make_mock_resp(200, [{"id": 5, "name": "incident"}])
    label_post_resp = _make_mock_resp(200)

    ctx_mgr = _make_mock_async_client(side_effect=[labels_resp, label_post_resp])

    with patch("httpx.AsyncClient", return_value=ctx_mgr):
        await client.add_label(42, "incident")

    inner = ctx_mgr.__aenter__.return_value
    assert inner.request.call_count == 2
    second_call = inner.request.call_args_list[1]
    assert second_call[0][0] == "POST"
    assert "issues/42/labels" in second_call[0][1]


# ------------------------------------------------------------------
# test_list_open_by_label
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_open_by_label(client: ForgejoClient):
    """Mock GET /issues with label filter — assert returns list."""
    mock_resp = _make_mock_resp(200, [
        {"number": 1, "title": "Issue 1", "state": "open"},
        {"number": 2, "title": "Issue 2", "state": "open"},
    ])
    ctx_mgr = _make_mock_async_client(response=mock_resp)

    with patch("httpx.AsyncClient", return_value=ctx_mgr):
        issues = await client.open_issues_by_label("monitoring")

    assert len(issues) == 2
    assert issues[0]["number"] == 1
    inner = ctx_mgr.__aenter__.return_value
    _, kwargs = inner.request.call_args
    assert kwargs["params"]["labels"] == "monitoring"
    assert kwargs["params"]["state"] == "open"


# ------------------------------------------------------------------
# test_label_id_caching
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_label_id_caching(client: ForgejoClient):
    """Resolve same label twice — assert only one GET /labels call."""
    # Create one ctx_mgr that returns three different responses for three calls
    labels_resp = _make_mock_resp(200, [{"id": 10, "name": "deprecation"}])
    issue_resp1 = _make_mock_resp(201, {"number": 1})
    issue_resp2 = _make_mock_resp(201, {"number": 2})

    # Each call to `httpx.AsyncClient()` creates a new ctx_mgr, so we need
    # separate patches for each create_issue call.  But the rate-limit delay
    # inside _api means each _api call opens a fresh client, so we must
    # handle this differently.

    # Simpler approach: patch the _resolve_label_ids to test caching directly,
    # and use a fresh ctx_mgr per _api call.

    # Sequence of calls:
    #   create_issue("First") -> _resolve_label_ids (GET labels) -> _api (POST issue)
    #   create_issue("Second") -> _resolve_label_ids (cached, no GET) -> _api (POST issue)
    # Total HTTP calls: 1 label GET + 2 issue POST = 3 requests.
    # But _api opens _api -> httpx.AsyncClient per call, so actually:
    #   3 separate httpx.AsyncClient() calls

    # Redisign: Each ctx_mgr is a separate httpx.AsyncClient() call.
    # We'll use a sequence of return values for the patch.

    ctx_mgr1 = _make_mock_async_client(side_effect=[labels_resp])
    ctx_mgr2 = _make_mock_async_client(response=issue_resp1)
    ctx_mgr3 = _make_mock_async_client(response=issue_resp2)

    from unittest.mock import Mock
    call_seq = Mock(side_effect=[ctx_mgr1, ctx_mgr2, ctx_mgr3])

    with patch("httpx.AsyncClient", side_effect=call_seq):
        # First issue — first call: ctx_mgr1 (for _resolve_label_ids), second call: ctx_mgr2 (for issue post)
        # But _api is called once per issue, so we need to handle the nested async client creation
        pass

    # Actually this is getting complex.  Let's simplify by just testing that
    # the caching works: the first create_issue makes 2 API calls, the second
    # makes only 1 (no labels GET).
    # Since _api creates a new httpx.AsyncClient for each call, we need
    # to provide enough mocks in sequence.

    # The simplest correct test: Use a call counter to verify
    # the labels endpoint is hit only once.

    count = {"get_labels": 0}

    class TrackingClient:
        """Minimal client mock that tracks GET /labels calls."""
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

        async def request(self, method, url, **kwargs):
            if "labels" in url and method == "GET":
                count["get_labels"] += 1
                resp = _make_mock_resp(200, [{"id": 10, "name": "deprecation"}])
                return resp
            resp = _make_mock_resp(201, {"number": 999})
            return resp

    with patch("httpx.AsyncClient", return_value=TrackingClient()):
        await client.create_issue("First", "", labels=["deprecation"])
        await client.create_issue("Second", "", labels=["deprecation"])

    # Should have hit /labels only once (cached on second call)
    assert count["get_labels"] == 1, f"Expected 1 labels GET, got {count['get_labels']}"


# ------------------------------------------------------------------
# test_forgejo_error
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forgejo_error(client: ForgejoClient):
    """API returns 403 — assert ForgejoError raised with status_code."""
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"

    ctx_mgr = _make_mock_async_client(response=mock_resp)

    with patch("httpx.AsyncClient", return_value=ctx_mgr):
        with pytest.raises(ForgejoError) as exc_info:
            await client.create_issue("Test", "body")

    assert exc_info.value.status_code == 403
    assert "Forbidden" in exc_info.value.message


# ------------------------------------------------------------------
# test_remove_label
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_label(client: ForgejoClient):
    """Mock GET issue labels then DELETE specific label — assert success."""
    get_labels_resp = _make_mock_resp(200, [
        {"id": 7, "name": "monitoring"},
        {"id": 8, "name": "incident"},
    ])
    delete_resp = _make_mock_resp(204)

    ctx_mgr = _make_mock_async_client(side_effect=[get_labels_resp, delete_resp])

    with patch("httpx.AsyncClient", return_value=ctx_mgr):
        await client.remove_label(42, "monitoring")

    inner = ctx_mgr.__aenter__.return_value
    assert inner.request.call_count == 2
    second_call = inner.request.call_args_list[1]
    assert second_call[0][0] == "DELETE"
    assert "labels/7" in second_call[0][1]


# ------------------------------------------------------------------
# test_remove_label_not_found
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_label_not_found(client: ForgejoClient):
    """Label not on the issue — no error, just warning."""
    get_labels_resp = _make_mock_resp(200, [{"id": 7, "name": "monitoring"}])

    ctx_mgr = _make_mock_async_client(response=get_labels_resp)

    with patch("httpx.AsyncClient", return_value=ctx_mgr):
        await client.remove_label(42, "nonexistent")

    inner = ctx_mgr.__aenter__.return_value
    assert inner.request.call_count == 1
