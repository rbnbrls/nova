import hmac
import hashlib
from app.security import verify_whatsapp_signature


def test_verify_whatsapp_signature():
    secret = "my_app_secret"
    body = b'{"object":"whatsapp_business_account","entry":[]}'
    h = hmac.new(secret.encode("utf-8"), body, hashlib.sha256)
    valid_sig = f"sha256={h.hexdigest()}"

    # Valid signature
    assert verify_whatsapp_signature(body, valid_sig, secret) is True

    # Invalid signature
    assert verify_whatsapp_signature(body, "sha256=wrongsignature", secret) is False

    # Invalid format (no prefix)
    assert verify_whatsapp_signature(body, h.hexdigest(), secret) is False

    # Empty inputs
    assert verify_whatsapp_signature(body, None, secret) is False
    assert verify_whatsapp_signature(body, valid_sig, "") is False
