"""Tests for WhatsApp OTP self-service linking (Phase 14)."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta

from app.main import app
from app.models import LinkWhatsAppStartRequest, LinkWhatsAppVerifyRequest


@pytest.fixture
def client():
    return TestClient(app)


# ------------------------ Model Tests ------------------------

def test_link_whatsapp_models_exist():
    """Verify request models have the correct fields."""
    start_req = LinkWhatsAppStartRequest(user="Ruben", number="31612345678")
    assert start_req.user == "Ruben"
    assert start_req.number == "31612345678"

    verify_req = LinkWhatsAppVerifyRequest(user="Ruben", code="123456")
    assert verify_req.user == "Ruben"
    assert verify_req.code == "123456"


# ------------------------ /start endpoint tests ------------------------

def test_start_success(client):
    """POST /dashboard/link-whatsapp/start returns code_sent on success."""
    mock_conn = AsyncMock()
    # user_id (fetchval), existing_owner (fetchval), rate_limit count (fetchval)
    mock_conn.fetchval.side_effect = [
        "ruben-user-uuid",  # user found
        None,               # number not claimed by another user
        0,                  # no recent code (rate limit OK)
    ]
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("app.main.send_whatsapp_otp", new_callable=AsyncMock) as mock_send_otp:
        mock_get_pool.return_value = mock_pool

        resp = client.post(
            "/dashboard/link-whatsapp/start",
            json={"user": "Ruben", "number": "31612345678"}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "code_sent"

        # Verify OTP was sent with cleaned number
        mock_send_otp.assert_called_once()
        args = mock_send_otp.call_args
        assert args[1]["code"] is not None
        assert len(args[1]["code"]) == 6

        # Verify code inserted into DB
        mock_conn.execute.assert_called_once()
        args, _ = mock_conn.execute.call_args
        assert "INSERT INTO channel_verification_codes" in args[0]


def test_start_user_not_found(client):
    """POST /dashboard/link-whatsapp/start returns 404 for unknown user."""
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = None  # user not found
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        resp = client.post(
            "/dashboard/link-whatsapp/start",
            json={"user": "Unknown", "number": "31612345678"}
        )
        assert resp.status_code == 404


def test_start_invalid_number(client):
    """POST /dashboard/link-whatsapp/start returns 400 for invalid number."""
    mock_conn = AsyncMock()
    mock_conn.fetchval.side_effect = [
        "ruben-user-uuid",  # user found
    ]
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        resp = client.post(
            "/dashboard/link-whatsapp/start",
            json={"user": "Ruben", "number": "abc123"}
        )
        assert resp.status_code == 400


def test_start_claim_conflict(client):
    """POST /dashboard/link-whatsapp/start rejects number linked to another user."""
    mock_conn = AsyncMock()
    # user_id (fetchval), existing_owner_name (fetchval)
    mock_conn.fetchval.side_effect = [
        "ruben-user-uuid",  # user found
        "Meral",            # number already linked to Meral
    ]
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        resp = client.post(
            "/dashboard/link-whatsapp/start",
            json={"user": "Ruben", "number": "31698765432"}
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "already linked" in detail.lower()
        # Should mention the current owner
        assert "Meral" in detail


def test_start_rate_limit_exceeded(client):
    """POST /dashboard/link-whatsapp/start returns 429 on rate limit."""
    mock_conn = AsyncMock()
    mock_conn.fetchval.side_effect = [
        "ruben-user-uuid",  # user found
        None,               # number not claimed by another user
        1,                  # recent code exists (rate limit hit)
    ]
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        resp = client.post(
            "/dashboard/link-whatsapp/start",
            json={"user": "Ruben", "number": "31612345678"}
        )
        assert resp.status_code == 429


def test_start_meta_api_failure(client):
    """POST /dashboard/link-whatsapp/start returns 502 when Meta API fails."""
    mock_conn = AsyncMock()
    mock_conn.fetchval.side_effect = [
        "ruben-user-uuid",  # user found
        None,               # number not claimed
        0,                  # no recent code
    ]
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("app.main.send_whatsapp_otp", new_callable=AsyncMock) as mock_send_otp:
        mock_get_pool.return_value = mock_pool
        mock_send_otp.side_effect = RuntimeError("Meta API error")

        resp = client.post(
            "/dashboard/link-whatsapp/start",
            json={"user": "Ruben", "number": "31612345678"}
        )
        assert resp.status_code == 502
        detail = resp.json()["detail"]
        assert "try again" in detail.lower()


# ------------------------ /verify endpoint tests ------------------------

def test_verify_success(client):
    """POST /dashboard/link-whatsapp/verify returns success with linked number."""
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = "ruben-user-uuid"  # user found
    mock_conn.fetchrow.return_value = {
        "id": "code-uuid",
        "whatsapp_number": "31612345678",
        "code": "123456",
        "attempts": 0,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool

        resp = client.post(
            "/dashboard/link-whatsapp/verify",
            json={"user": "Ruben", "code": "123456"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["linked_number"] == "31612345678"

        # Verify DB operations: increment attempts, link number, expire code
        calls = mock_conn.execute.call_args_list
        assert len(calls) >= 2  # at minimum: link + expire
        # Check link query
        link_args = [c[0][0] for c in calls]
        assert any("INSERT INTO user_preferences" in a for a in link_args)
        assert any("UPDATE channel_verification_codes SET attempts = 99" in a for a in link_args)


def test_verify_wrong_code(client):
    """POST /dashboard/link-whatsapp/verify returns 400 for wrong code."""
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = "ruben-user-uuid"  # user found
    mock_conn.fetchrow.return_value = {
        "id": "code-uuid",
        "whatsapp_number": "31612345678",
        "code": "123456",
        "attempts": 0,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool

        resp = client.post(
            "/dashboard/link-whatsapp/verify",
            json={"user": "Ruben", "code": "999999"}
        )
        assert resp.status_code == 400
        assert "attempts remaining" in resp.json()["detail"].lower()

        # Verify attempt was incremented before checking code
        mock_conn.execute.assert_called_once()
        assert "SET attempts = attempts + 1" in mock_conn.execute.call_args[0][0]


def test_verify_exhausted_attempts(client):
    """POST /dashboard/link-whatsapp/verify returns 400 when attempts exhausted."""
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = "ruben-user-uuid"
    # Row with attempts=2 (one more attempt would reach 3 and expire)
    mock_conn.fetchrow.return_value = {
        "id": "code-uuid",
        "whatsapp_number": "31612345678",
        "code": "123456",
        "attempts": 2,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool

        resp = client.post(
            "/dashboard/link-whatsapp/verify",
            json={"user": "Ruben", "code": "999999"}
        )
        assert resp.status_code == 400
        # Should mention no attempts remaining
        assert "no attempts remaining" in resp.json()["detail"].lower() or \
               "request a new code" in resp.json()["detail"].lower()


def test_verify_expired_code(client):
    """POST /dashboard/link-whatsapp/verify returns 400 for expired code."""
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = "ruben-user-uuid"  # user found
    # No active code found (fetchrow returns None)
    mock_conn.fetchrow.return_value = None
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool

        resp = client.post(
            "/dashboard/link-whatsapp/verify",
            json={"user": "Ruben", "code": "123456"}
        )
        assert resp.status_code == 400


def test_verify_user_not_found(client):
    """POST /dashboard/link-whatsapp/verify returns 404 for unknown user."""
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = None  # user not found
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        resp = client.post(
            "/dashboard/link-whatsapp/verify",
            json={"user": "Unknown", "code": "123456"}
        )
        assert resp.status_code == 404
