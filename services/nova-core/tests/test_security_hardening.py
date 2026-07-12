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
