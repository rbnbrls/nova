"""Security helpers for webhook signature verification."""
from __future__ import annotations

import hmac
import hashlib


def verify_whatsapp_signature(body: bytes, signature_header: str | None, secret: str) -> bool:
    """Verify that the raw webhook body matches the X-Hub-Signature-256 header."""
    if not signature_header or not secret:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected_hex = signature_header[len("sha256="):]
    h = hmac.new(secret.encode("utf-8"), body, hashlib.sha256)
    actual_hex = h.hexdigest()
    return hmac.compare_digest(actual_hex, expected_hex)
