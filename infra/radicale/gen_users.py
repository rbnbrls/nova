"""Generate htpasswd-compatible users file from env vars.

Called at container startup before launching Radicale. Uses bcrypt
from /venv if available, otherwise falls back to SHA-512 crypt.
"""
from __future__ import annotations

import os
import sys

CALDAV_USERNAME = os.environ.get("CALDAV_USERNAME", "")
CALDAV_PASSWORD = os.environ.get("CALDAV_PASSWORD", "")
OUTPUT_PATH = os.environ.get("CALDAV_HTPASSWD_PATH", "/data/users.htpasswd")


def _sha512_crypt(password: str) -> str:
    import hashlib
    import base64

    salt = base64.b64encode(os.urandom(16)).decode("ascii").rstrip("=")
    digest = hashlib.sha512(salt.encode() + password.encode()).hexdigest()
    return f"$6${salt}${digest}"


def main() -> None:
    if not CALDAV_USERNAME or not CALDAV_PASSWORD:
        print("[gen_users] CALDAV_USERNAME or CALDAV_PASSWORD not set — skipping user file")
        sys.exit(0)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    try:
        sys.path.insert(0, "/venb/lib/python3.*/site-packages")
        import bcrypt

        hashed = bcrypt.hashpw(CALDAV_PASSWORD.encode(), bcrypt.gensalt()).decode()
    except ImportError:
        hashed = _sha512_crypt(CALDAV_PASSWORD)

    with open(OUTPUT_PATH, "w") as f:
        f.write(f"{CALDAV_USERNAME}:{hashed}\n")

    print(f"[gen_users] Wrote user '{CALDAV_USERNAME}' to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
