import pytest
import hmac
import hashlib
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings

client = TestClient(app)


def test_whatsapp_handshake_success():
    settings.whatsapp_verify_token = "mysecrettoken"
    resp = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "mysecrettoken",
            "hub.challenge": "hello1234"
        }
    )
    assert resp.status_code == 200
    assert resp.text == "hello1234"


def test_whatsapp_handshake_failure():
    settings.whatsapp_verify_token = "mysecrettoken"
    resp = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrongtoken",
            "hub.challenge": "hello1234"
        }
    )
    assert resp.status_code == 403


def test_whatsapp_webhook_missing_signature():
    resp = client.post("/webhooks/whatsapp", json={"test": "payload"})
    assert resp.status_code == 401


def test_whatsapp_webhook_invalid_signature():
    resp = client.post(
        "/webhooks/whatsapp",
        headers={"X-Hub-Signature-256": "sha256=invalidhash"},
        json={"test": "payload"}
    )
    assert resp.status_code == 401


def test_whatsapp_webhook_valid_signature():
    settings.whatsapp_app_secret = "appsecret"
    payload = b'{"test":"payload"}'
    
    # Calculate correct signature
    h = hmac.new(b"appsecret", payload, hashlib.sha256)
    signature = f"sha256={h.hexdigest()}"
    
    resp = client.post(
        "/webhooks/whatsapp",
        headers={"X-Hub-Signature-256": signature},
        content=payload
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "accepted"}


@pytest.mark.asyncio
async def test_webhook_unrecognized_number_refusal():
    from unittest.mock import AsyncMock, patch
    from app.whatsapp import process_incoming_whatsapp
    
    # Configure user settings: Ruben is authorized, others are not
    settings.nova_whatsapp_users = "31612345678:Ruben"
    
    # Reload _WHATSAPP_USERS mapping to pick up settings change
    from app import identity
    identity._WHATSAPP_USERS = identity._parse_whatsapp_map()
    
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "31699999999", # Unrecognized
                        "text": {"body": "Hello"}
                    }]
                }
            }]
        }]
    }
    
    with patch("app.whatsapp.send_whatsapp_message", new_callable=AsyncMock) as mock_send, \
         patch("app.whatsapp.run_agent", new_callable=AsyncMock) as mock_agent:
         
        await process_incoming_whatsapp(payload)
        
        # Verify refusal sent
        mock_send.assert_called_once_with("31699999999", "Sorry, you are not authorized to use this household assistant.")
        # Verify LLM was skipped
        mock_agent.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_authorized_number_success():
    from unittest.mock import AsyncMock, patch
    from app.whatsapp import process_incoming_whatsapp
    
    settings.nova_whatsapp_users = "31612345678:Ruben"
    from app import identity
    identity._WHATSAPP_USERS = identity._parse_whatsapp_map()
    
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "31612345678", # Ruben
                        "text": {"body": "What's on the calendar?"}
                    }]
                }
            }]
        }]
    }
    
    with patch("app.whatsapp.send_whatsapp_message", new_callable=AsyncMock) as mock_send, \
         patch("app.whatsapp.run_agent", new_callable=AsyncMock) as mock_agent:
         
        mock_agent.return_value = "Here is your calendar..."
        await process_incoming_whatsapp(payload)
        
        # Verify LLM run and response sent
        mock_agent.assert_called_once_with("What's on the calendar?", user="Ruben")
        mock_send.assert_called_once_with("31612345678", "Here is your calendar...")

