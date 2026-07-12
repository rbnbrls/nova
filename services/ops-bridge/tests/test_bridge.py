import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app import _fingerprint, app
from fastapi.testclient import TestClient
import httpx

client = TestClient(app)


def test_fingerprint():
    fp = _fingerprint("TestAlert", "prod-stream")
    assert len(fp) == 10
    assert fp == _fingerprint("TestAlert", "prod-stream")


def test_webhook_auth_failure():
    with patch("app.BRIDGE_TOKEN", "secret-token"):
        resp = client.post("/webhooks/openobserve", headers={"X-Bridge-Token": "wrong-token"})
        assert resp.status_code == 401


def test_webhook_auth_constant_time():
    import hmac
    with patch("app.BRIDGE_TOKEN", "secret-token"), \
         patch("hmac.compare_digest", wraps=hmac.compare_digest) as mock_compare:
        resp = client.post("/webhooks/openobserve", headers={"X-Bridge-Token": "wrong-token"})
        assert resp.status_code == 401
        mock_compare.assert_called_once_with("wrong-token", "secret-token")


def test_webhook_missing_token():
    """Missing X-Bridge-Token header returns 401 without leaking details."""
    with patch("app.BRIDGE_TOKEN", "secret-token"):
        resp = client.post("/webhooks/openobserve", headers={})
        assert resp.status_code == 401
        assert resp.json() == {"detail": "bad or missing X-Bridge-Token"}


@pytest.mark.asyncio
async def test_webhook_new_issue():
    with patch("app.BRIDGE_TOKEN", "secret-token"), \
         patch("app.FORGEJO_TOKEN", "forgejo-token"), \
         patch("app.ALERT_LABELS", ["incident"]):

        mock_resp_search = MagicMock(spec=httpx.Response)
        mock_resp_search.json = MagicMock(return_value=[])
        mock_resp_search.status_code = 200

        mock_resp_labels = MagicMock(spec=httpx.Response)
        mock_resp_labels.json = MagicMock(return_value=[{"name": "incident", "id": 1}])
        mock_resp_labels.status_code = 200

        mock_resp_create = MagicMock(spec=httpx.Response)
        mock_resp_create.json = MagicMock(return_value={"number": 42})
        mock_resp_create.status_code = 201

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client

        def mock_get(url, *args, **kwargs):
            if "/issues" in url:
                return mock_resp_search
            elif "/labels" in url:
                return mock_resp_labels
            raise ValueError(f"Unexpected get URL: {url}")

        mock_client.get.side_effect = mock_get
        mock_client.post.return_value = mock_resp_create

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("app._label_ids", {}):
                resp = client.post(
                    "/webhooks/openobserve",
                    headers={"X-Bridge-Token": "secret-token"},
                    json={"alert_name": "CPUAlert", "stream_name": "server1"}
                )
                assert resp.status_code == 200
                assert resp.json() == {"action": "created", "issue": 42}
                mock_client.post.assert_called_once()
                args, kwargs = mock_client.post.call_args
                assert "/issues" in args[0]
                assert kwargs["json"]["title"].startswith("[monitoring] CPUAlert on server1")
                assert kwargs["json"]["labels"] == [1]


@pytest.mark.asyncio
async def test_webhook_dedup_comment():
    with patch("app.BRIDGE_TOKEN", "secret-token"), \
         patch("app.FORGEJO_TOKEN", "forgejo-token"):

        mock_resp_search = MagicMock(spec=httpx.Response)
        mock_resp_search.json = MagicMock(return_value=[{"number": 101}])
        mock_resp_search.status_code = 200

        mock_resp_comment = MagicMock(spec=httpx.Response)
        mock_resp_comment.status_code = 201

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = mock_resp_search
        mock_client.post.return_value = mock_resp_comment

        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = client.post(
                "/webhooks/openobserve",
                headers={"X-Bridge-Token": "secret-token"},
                json={"alert_name": "CPUAlert", "stream_name": "server1"}
            )
            assert resp.status_code == 200
            assert resp.json() == {"action": "commented", "issue": 101}
            mock_client.post.assert_called_once()
            args, kwargs = mock_client.post.call_args
            assert "/issues/101/comments" in args[0]
