from app.identity import user_from_whatsapp, HOUSEHOLD, User, _parse_whatsapp_map
from app.config import settings
from unittest.mock import patch


def test_parse_whatsapp_map():
    with patch.object(settings, "nova_whatsapp_users", "12345:Ruben, 67890:Meral, invalid_entry"):
        mapping = _parse_whatsapp_map()
        assert mapping["12345"] == User(name="Ruben")
        assert mapping["67890"] == User(name="Meral")
        assert "invalid_entry" not in mapping


def test_user_from_whatsapp():
    mock_users = {"12345": User(name="Ruben")}
    with patch("app.identity._WHATSAPP_USERS", mock_users):
        assert user_from_whatsapp("12345") == User(name="Ruben")
        assert user_from_whatsapp("+12345") == User(name="Ruben")
        assert user_from_whatsapp("99999") == HOUSEHOLD
