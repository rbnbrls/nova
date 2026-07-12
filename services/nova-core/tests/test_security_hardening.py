from __future__ import annotations

from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from app.config import settings
from app.main import app


def test_chat_completions_authentication():
    client = TestClient(app)
    
    # Store original token
    original_token = settings.nova_api_token
    
    try:
        # Set token for testing
        settings.nova_api_token = "test-secret-token"
        
        # 1. Request without Authorization header -> 401
        resp = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "Hello"}]}
        )
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Unauthorized"}
        
        # 2. Request with invalid format Authorization header -> 401
        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "test-secret-token"},
            json={"messages": [{"role": "user", "content": "Hello"}]}
        )
        assert resp.status_code == 401
        
        # 3. Request with wrong token -> 401
        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer wrong-token"},
            json={"messages": [{"role": "user", "content": "Hello"}]}
        )
        assert resp.status_code == 401
        
        # 4. Request with correct token -> 200
        with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "Hello back!"
            resp = client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-secret-token"},
                json={"messages": [{"role": "user", "content": "Hello"}]}
            )
            assert resp.status_code == 200
            assert resp.json()["choices"][0]["message"]["content"] == "Hello back!"
            mock_run.assert_called_once()
            
        # 5. Disable token (empty string) -> 200 without header
        settings.nova_api_token = ""
        with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "Hello back!"
            resp = client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "Hello"}]}
            )
            assert resp.status_code == 200
            assert resp.json()["choices"][0]["message"]["content"] == "Hello back!"
            mock_run.assert_called_once()

    finally:
        settings.nova_api_token = original_token


def test_auth_blocks_user_attribution_ordering():
    client = TestClient(app)
    original_token = settings.nova_api_token
    try:
        settings.nova_api_token = "test-secret-token"

        # Case 1: No auth header + user= query param -> 401, run_agent NOT called
        with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
            resp = client.post(
                "/v1/chat/completions?user=Ruben",
                json={"messages": [{"role": "user", "content": "Hello"}]}
            )
            assert resp.status_code == 401
            mock_run.assert_not_called()

        # Case 2: No auth header + user= in body -> 401, run_agent NOT called
        with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
            resp = client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "Hello"}], "user": "Ruben"}
            )
            assert resp.status_code == 401
            mock_run.assert_not_called()

        # Case 3: Valid auth + user= query param -> 200, run_agent called WITH user="Ruben"
        with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "Hello Ruben!"
            resp = client.post(
                "/v1/chat/completions?user=Ruben",
                headers={"Authorization": "Bearer test-secret-token"},
                json={"messages": [{"role": "user", "content": "Hello"}]}
            )
            assert resp.status_code == 200
            mock_run.assert_called_once()
            _, kwargs = mock_run.call_args
            assert kwargs.get("user") == "Ruben"

    finally:
        settings.nova_api_token = original_token


def test_auth_error_response_consistency():
    client = TestClient(app)
    original_token = settings.nova_api_token
    try:
        settings.nova_api_token = "test-secret-token"
        body = {"messages": [{"role": "user", "content": "Hello"}]}

        # Missing header
        resp_missing = client.post("/v1/chat/completions", json=body)
        # No Bearer prefix
        resp_no_bearer = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "test-secret-token"},
            json=body
        )
        # Wrong token
        resp_wrong = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer wrong-token"},
            json=body
        )

        expected = {"detail": "Unauthorized"}
        for resp in [resp_missing, resp_no_bearer, resp_wrong]:
            assert resp.status_code == 401
            assert resp.json() == expected

    finally:
        settings.nova_api_token = original_token
