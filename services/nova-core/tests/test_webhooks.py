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
    from app.channels.whatsapp import process_incoming_whatsapp
    from app import identity
    
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
    
    with patch("app.channels.whatsapp.send_whatsapp_message", new_callable=AsyncMock) as mock_send, \
         patch("app.channels.whatsapp.run_agent", new_callable=AsyncMock) as mock_agent, \
         patch("app.identity.user_from_whatsapp", new_callable=AsyncMock) as mock_resolve:
         
        mock_resolve.return_value = identity.HOUSEHOLD
        await process_incoming_whatsapp(payload)
        
        # Verify refusal sent
        mock_send.assert_called_once_with("31699999999", "Sorry, you are not authorized to use this household assistant.")
        # Verify LLM was skipped
        mock_agent.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_authorized_number_success():
    from unittest.mock import AsyncMock, patch
    from app.channels.whatsapp import process_incoming_whatsapp
    from app import identity
    
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
    
    with patch("app.channels.whatsapp.send_whatsapp_message", new_callable=AsyncMock) as mock_send, \
         patch("app.channels.whatsapp.run_agent", new_callable=AsyncMock) as mock_agent, \
         patch("app.identity.user_from_whatsapp", new_callable=AsyncMock) as mock_resolve:
         
        mock_resolve.return_value = identity.User(name="Ruben")
        mock_agent.return_value = "Here is your calendar..."
        await process_incoming_whatsapp(payload)
        
        # Verify LLM run and response sent
        mock_agent.assert_called_once_with("What's on the calendar?", user="Ruben")
        mock_send.assert_called_once_with("31612345678", "Here is your calendar...")


# ---------------------------------------------------------------------------
# Phase 9: Webhook endpoint edge case tests
# ---------------------------------------------------------------------------

def _sig_header(secret: str, body: bytes) -> str:
    h = hmac.new(secret.encode(), body, hashlib.sha256)
    return f"sha256={h.hexdigest()}"


def test_whatsapp_webhook_signature_raw_body_used():
    settings.whatsapp_app_secret = "test_secret"
    body1 = b'{"key":"value"}'
    sig1 = _sig_header("test_secret", body1)
    resp1 = client.post(
        "/webhooks/whatsapp",
        content=body1,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig1,
        },
    )
    assert resp1.status_code == 200 or resp1.status_code == 400

    body2 = b'{"key": "value"}'
    resp2 = client.post(
        "/webhooks/whatsapp",
        content=body2,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig1,
        },
    )
    assert resp2.status_code == 401


def test_whatsapp_webhook_missing_header():
    settings.whatsapp_app_secret = "test_secret"
    resp = client.post(
        "/webhooks/whatsapp",
        content=b'{"test": true}',
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 401


def test_whatsapp_webhook_invalid_json_body():
    settings.whatsapp_app_secret = "test_secret"
    body = b'{"broken": }'
    sig = _sig_header("test_secret", body)
    resp = client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
        },
    )
    assert resp.status_code == 400


def test_whatsapp_webhook_non_message_payload():
    settings.whatsapp_app_secret = "test_secret"
    body = b'{"entry": [{"changes": [{"value": {"statuses": [{"id": "abc"}]}}]}]}'
    sig = _sig_header("test_secret", body)
    resp = client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
        },
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Phase 37: Image message tests (TDD RED — failing before implementation)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_whatsapp_process_incoming_image():
    """WhatsAppAdapter.process_incoming extracts media_id from image payloads."""
    from app.channels.whatsapp import WhatsAppAdapter

    adapter = WhatsAppAdapter()
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "31612345678",
                        "image": {"id": "media-id-123"}
                    }]
                }
            }]
        }]
    }

    result = await adapter.process_incoming(payload)
    assert result is not None
    assert result.media_id == "media-id-123"
    assert result.media_type == "image"


@pytest.mark.asyncio
async def test_whatsapp_process_incoming_text_still_works():
    """WhatsAppAdapter.process_incoming still handles text messages."""
    from app.channels.whatsapp import WhatsAppAdapter

    adapter = WhatsAppAdapter()
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "31612345678",
                        "text": {"body": "Hello"}
                    }]
                }
            }]
        }]
    }

    result = await adapter.process_incoming(payload)
    assert result is not None
    assert result.text == "Hello"
    assert result.media_id is None
    assert result.media_type is None


@pytest.mark.asyncio
async def test_whatsapp_image_non_message_payload_still_skipped():
    """WhatsAppAdapter.process_incoming still returns None for non-message payloads."""
    from app.channels.whatsapp import WhatsAppAdapter

    adapter = WhatsAppAdapter()
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "statuses": [{"id": "abc"}]
                }
            }]
        }]
    }

    result = await adapter.process_incoming(payload)
    assert result is None


@pytest.mark.asyncio
async def test_download_whatsapp_media_no_token():
    """download_whatsapp_media returns None when whatsapp_access_token is empty."""
    from app.channels.whatsapp import download_whatsapp_media
    from app.config import settings

    settings.whatsapp_access_token = ""
    result = await download_whatsapp_media("test-media-id")
    assert result is None


@pytest.mark.asyncio
async def test_download_whatsapp_media_success():
    """download_whatsapp_media returns bytes when Meta API succeeds."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.channels.whatsapp import download_whatsapp_media
    from app.config import settings

    settings.whatsapp_access_token = "valid_token"
    with patch("app.channels.whatsapp.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        # httpx response methods (raise_for_status, json, content) are synchronous
        mock_resp_meta = MagicMock()
        mock_resp_meta.json.return_value = {"url": "https://cdn.meta.com/photo.jpg"}
        mock_resp_meta.raise_for_status.return_value = None

        mock_resp_dl = MagicMock()
        mock_resp_dl.content = b"fake-image-bytes"
        mock_resp_dl.raise_for_status.return_value = None

        mock_client.get.side_effect = [mock_resp_meta, mock_resp_dl]

        result = await download_whatsapp_media("media-id-456")
        assert result == b"fake-image-bytes"
        assert mock_client.get.call_count == 2


@pytest.mark.asyncio
async def test_download_whatsapp_media_http_failure():
    """download_whatsapp_media returns None on Meta API HTTP error."""
    import httpx
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.channels.whatsapp import download_whatsapp_media
    from app.config import settings

    settings.whatsapp_access_token = "valid_token"
    with patch("app.channels.whatsapp.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        # Simulate HTTP error on the first GET
        mock_client.get.side_effect = httpx.HTTPStatusError(
            "403 Forbidden", request=None, response=MagicMock(status_code=403)
        )

        result = await download_whatsapp_media("media-id-789")
        assert result is None


@pytest.mark.asyncio
async def test_webhook_image_message_flow():
    """Image messages go through download → analyze → synthetic context → agent."""
    from unittest.mock import AsyncMock, patch
    from app.channels.whatsapp import process_incoming_whatsapp
    from app import identity

    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "31612345678",
                        "image": {"id": "media-id-123"}
                    }]
                }
            }]
        }]
    }

    mock_extraction = {
        "summary": "School letter about parent meeting",
        "events": [{
            "title": "Parent Meeting",
            "start": "2026-09-05T10:00:00",
            "end": "2026-09-05T11:00:00",
            "description": "School parent meeting",
        }],
        "tasks": [{
            "title": "Submit permission slip",
            "assignee": "Ruben",
            "due_at": "2026-08-20",
        }],
    }

    with patch("app.channels.whatsapp.send_whatsapp_message", new_callable=AsyncMock) as mock_send, \
         patch("app.channels.whatsapp.run_agent", new_callable=AsyncMock) as mock_agent, \
         patch("app.identity.user_from_whatsapp", new_callable=AsyncMock) as mock_resolve, \
         patch("app.channels.whatsapp.download_whatsapp_media", new_callable=AsyncMock) as mock_dl, \
         patch("app.vision.analyze_image", new_callable=AsyncMock) as mock_vision:

        mock_resolve.return_value = identity.User(name="Ruben")
        mock_dl.return_value = b"fake-image-bytes"
        mock_vision.return_value = mock_extraction
        mock_agent.return_value = "I've analyzed the photo you sent."

        await process_incoming_whatsapp(payload)

        mock_dl.assert_called_once_with("media-id-123")
        mock_vision.assert_called_once_with(b"fake-image-bytes")

        # Agent should receive synthetic message with the vision analysis
        call_text = mock_agent.call_args[0][0]
        assert "[User sent a photo." in call_text
        assert "School letter" in call_text
        assert "Parent Meeting" in call_text

        mock_send.assert_called_once_with("31612345678", "I've analyzed the photo you sent.")


@pytest.mark.asyncio
async def test_webhook_image_download_failure():
    """process_incoming_whatsapp sends friendly error when media download fails."""
    from unittest.mock import AsyncMock, patch
    from app.channels.whatsapp import process_incoming_whatsapp
    from app import identity

    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "31612345678",
                        "image": {"id": "media-id-123"}
                    }]
                }
            }]
        }]
    }

    with patch("app.channels.whatsapp.send_whatsapp_message", new_callable=AsyncMock) as mock_send, \
         patch("app.identity.user_from_whatsapp", new_callable=AsyncMock) as mock_resolve, \
         patch("app.channels.whatsapp.download_whatsapp_media", new_callable=AsyncMock, create=True) as mock_dl:

        mock_resolve.return_value = identity.User(name="Ruben")
        mock_dl.return_value = None  # download failed

        await process_incoming_whatsapp(payload)

        mock_send.assert_called_once()
        error_msg = mock_send.call_args[0][1]
        assert "could not download" in error_msg.lower()


@pytest.mark.asyncio
async def test_webhook_image_analysis_failure():
    """process_incoming_whatsapp sends friendly error when vision analysis fails."""
    from unittest.mock import AsyncMock, patch
    from app.channels.whatsapp import process_incoming_whatsapp
    from app import identity

    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "31612345678",
                        "image": {"id": "media-id-123"}
                    }]
                }
            }]
        }]
    }

    error_extraction = {
        "summary": "", "events": [], "tasks": [],
        "error": "Ollama connection error",
    }

    with patch("app.channels.whatsapp.send_whatsapp_message", new_callable=AsyncMock) as mock_send, \
         patch("app.identity.user_from_whatsapp", new_callable=AsyncMock) as mock_resolve, \
         patch("app.channels.whatsapp.download_whatsapp_media", new_callable=AsyncMock) as mock_dl, \
         patch("app.vision.analyze_image", new_callable=AsyncMock) as mock_vision:

        mock_resolve.return_value = identity.User(name="Ruben")
        mock_dl.return_value = b"fake-image-bytes"
        mock_vision.return_value = error_extraction  # analysis failed

        await process_incoming_whatsapp(payload)

        mock_send.assert_called_once()
        error_msg = mock_send.call_args[0][1]
        assert "trouble reading" in error_msg.lower()


@pytest.mark.asyncio
async def test_webhook_authorized_number_success_image_preserved():
    """Text-based messages still work after image handling is added — no regression."""
    from unittest.mock import AsyncMock, patch
    from app.channels.whatsapp import process_incoming_whatsapp
    from app import identity

    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "31612345678",
                        "text": {"body": "What's new?"}
                    }]
                }
            }]
        }]
    }

    with patch("app.channels.whatsapp.send_whatsapp_message", new_callable=AsyncMock) as mock_send, \
         patch("app.channels.whatsapp.run_agent", new_callable=AsyncMock) as mock_agent, \
         patch("app.identity.user_from_whatsapp", new_callable=AsyncMock) as mock_resolve:

        mock_resolve.return_value = identity.User(name="Ruben")
        mock_agent.return_value = "Nothing new today."

        await process_incoming_whatsapp(payload)

        mock_agent.assert_called_once_with("What's new?", user="Ruben")
        mock_send.assert_called_once_with("31612345678", "Nothing new today.")

