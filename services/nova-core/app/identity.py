"""Map an inbound channel identity to a household user.

Every channel (WhatsApp, voice, API) resolves to one of: Ruben, Meral, household.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import settings


@dataclass(frozen=True)
class User:
    name: str


HOUSEHOLD = User(name="household")


def _parse_whatsapp_map() -> dict[str, User]:
    mapping: dict[str, User] = {}
    for entry in settings.nova_whatsapp_users.split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        number, name = entry.split(":", 1)
        mapping[number.strip()] = User(name=name.strip())
    return mapping


_WHATSAPP_USERS = _parse_whatsapp_map()


def user_from_whatsapp(sender_number: str) -> User:
    """Resolve a WhatsApp E.164 sender number (no '+') to a household user."""
    return _WHATSAPP_USERS.get(sender_number.lstrip("+"), HOUSEHOLD)
