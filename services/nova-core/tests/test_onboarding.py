import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_get_preferences(client):
    mock_rows = [
        {
            "name": "Ruben",
            "whatsapp_number": "31612345678",
            "dnd_enabled": True,
            "dnd_start": datetime.strptime("22:00", "%H:%M").time(),
            "dnd_end": datetime.strptime("07:00", "%H:%M").time(),
            "morning_briefing_enabled": True,
            "morning_briefing_time": datetime.strptime("07:00", "%H:%M").time(),
            "weekly_briefing_enabled": True,
            "weekly_briefing_day": 1,
            "weekly_briefing_time": datetime.strptime("09:00", "%H:%M").time(),
        },
        {
            "name": "Meral",
            "whatsapp_number": None,
            "dnd_enabled": False,
            "dnd_start": None,
            "dnd_end": None,
            "morning_briefing_enabled": False,
            "morning_briefing_time": None,
            "weekly_briefing_enabled": False,
            "weekly_briefing_day": None,
            "weekly_briefing_time": None,
        }
    ]
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = mock_rows
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        resp = client.get("/api/preferences")
        assert resp.status_code == 200
        data = resp.json()
        assert "Ruben" in data
        assert "Meral" in data
        assert data["Ruben"]["whatsapp_number"] == "31612345678"
        assert data["Ruben"]["dnd_enabled"] is True
        assert data["Meral"]["whatsapp_number"] == ""
        assert data["Meral"]["dnd_enabled"] is False


def test_request_code_success(client):
    mock_conn = AsyncMock()
    # existing_owner is None, then user_id
    mock_conn.fetchval.side_effect = [None, "ruben-user-uuid"]
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("app.whatsapp.send_whatsapp_message", new_callable=AsyncMock) as mock_send_wa:
        mock_get_pool.return_value = mock_pool
        
        resp = client.post(
            "/api/preferences/request-code",
            json={"user": "Ruben", "number": "+31612345678"}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "code_sent"
        
        # Verify inserted into database
        mock_conn.execute.assert_called_once()
        args, kwargs = mock_conn.execute.call_args
        assert "INSERT INTO channel_verification_codes" in args[0]
        assert args[1] == "ruben-user-uuid"
        assert args[2] == "31612345678"  # cleaned
        
        # Verify WhatsApp sent
        mock_send_wa.assert_called_once()
        assert "verification code" in mock_send_wa.call_args[0][1]


def test_request_code_reject_already_linked(client):
    mock_conn = AsyncMock()
    # existing_owner is Meral
    mock_conn.fetchval.return_value = "Meral"
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        resp = client.post(
            "/api/preferences/request-code",
            json={"user": "Ruben", "number": "31612345678"}
        )
        assert resp.status_code == 400
        assert "already linked to Meral" in resp.json()["detail"]


def test_verify_code_success(client):
    mock_conn = AsyncMock()
    # user_id, active code row
    mock_conn.fetchval.return_value = "ruben-user-uuid"
    mock_conn.fetchrow.return_value = {
        "id": "code-uuid",
        "whatsapp_number": "31612345678",
        "code": "123456",
        "attempts": 0,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5)
    }
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        resp = client.post(
            "/api/preferences/verify-code",
            json={"user": "Ruben", "code": "123456"}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        assert resp.json()["linked_number"] == "31612345678"
        
        # Verify attempts increment and linking
        calls = mock_conn.execute.call_args_list
        assert len(calls) == 3
        assert "UPDATE channel_verification_codes SET attempts = attempts + 1" in calls[0][0][0]
        assert "INSERT INTO user_preferences" in calls[1][0][0]
        assert "UPDATE channel_verification_codes SET attempts = 99" in calls[2][0][0]


def test_verify_code_incorrect_attempts_exceeded(client):
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = "ruben-user-uuid"
    mock_conn.fetchrow.return_value = {
        "id": "code-uuid",
        "whatsapp_number": "31612345678",
        "code": "123456",
        "attempts": 2,  # 2 previous attempts
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5)
    }
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        
        # Incorrect code: 999999
        resp = client.post(
            "/api/preferences/verify-code",
            json={"user": "Ruben", "code": "999999"}
        )
        assert resp.status_code == 400
        assert "Incorrect verification code" in resp.json()["detail"]
        
        # Attempts updated
        mock_conn.execute.assert_called_once()
        assert "UPDATE channel_verification_codes SET attempts = attempts + 1" in mock_conn.execute.call_args[0][0]


def test_save_briefing_preferences_success(client):
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = "ruben-user-uuid"
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch("app.main.db.get_pool", new_callable=AsyncMock) as mock_get_pool:
        mock_get_pool.return_value = mock_pool
        resp = client.post(
            "/api/preferences/briefings",
            json={
                "user": "Ruben",
                "morning_enabled": True,
                "morning_time": "08:30",
                "weekly_enabled": False,
                "weekly_day": 2,
                "weekly_time": "10:00",
            }
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        
        # Verify inserted into database
        mock_conn.execute.assert_called_once()
        args, kwargs = mock_conn.execute.call_args
        assert "INSERT INTO user_preferences" in args[0]
        assert args[1] == "ruben-user-uuid"
        assert args[2] is True

