"""Map an inbound channel identity to a household user.

Every channel (WhatsApp, voice, API) resolves to one of: Ruben, Meral, household.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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


_WHATSAPP_USERS: dict[str, User] = {}  # Retained as empty for compatibility


async def user_from_whatsapp(sender_number: str) -> User:
    """Resolve a WhatsApp E.164 sender number (no '+') to a household user."""
    from .db import get_pool
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT u.name
                FROM user_preferences up
                JOIN users u ON up.user_id = u.id
                WHERE up.whatsapp_number = $1
                """,
                sender_number.lstrip("+")
            )
            if row:
                return User(name=row["name"])
    except Exception as e:
        print(f"[ERROR] DB error resolving WhatsApp user: {e}")
    return HOUSEHOLD


async def get_all_whatsapp_users() -> dict[str, User]:
    """Retrieve all mapped WhatsApp numbers and their corresponding Users from the DB."""
    from .db import get_pool
    mapping = {}
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT up.whatsapp_number, u.name
                FROM user_preferences up
                JOIN users u ON up.user_id = u.id
                WHERE up.whatsapp_number IS NOT NULL
                """
            )
            for r in rows:
                mapping[r["whatsapp_number"]] = User(name=r["name"])
    except Exception as e:
        print(f"[ERROR] DB error getting all WhatsApp users: {e}")
    return mapping


async def is_user_in_dnd(user_name: str) -> bool:
    """Check if DND is enabled and active for the user at the current local time."""
    import zoneinfo
    from .db import get_pool
    
    tz = zoneinfo.ZoneInfo(settings.nova_timezone)
    now_local = datetime.now(tz)
    current_time = now_local.time()
    
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT up.dnd_enabled, up.dnd_start, up.dnd_end
                FROM user_preferences up
                JOIN users u ON up.user_id = u.id
                WHERE u.name = $1
                """,
                user_name
            )
            if row and row["dnd_enabled"] and row["dnd_start"] and row["dnd_end"]:
                start = row["dnd_start"]
                end = row["dnd_end"]
                if start <= end:
                    return start <= current_time <= end
                else:  # Overnight window
                    return current_time >= start or current_time <= end
    except Exception as e:
        print(f"[ERROR] DND check failed for {user_name}: {e}")
    return False


