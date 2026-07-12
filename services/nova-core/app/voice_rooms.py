"""In-memory room session tracking for voice satellite identity.

Each voice satellite (ESPHome/HA Assist) maps to a room_id. This module
tracks which user is actively speaking at each room via a TTL-based
in-memory session store, falling back to DB-configured room defaults
and ultimately to "household".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .db import get_pool


@dataclass(frozen=True)
class RoomSession:
    room_id: str
    active_user: str | None
    last_activity: datetime


class RoomSessionManager:
    """Manages per-room active user sessions with TTL-based expiry.

    Fallback chain for get_active_user():
        1. Active in-memory session (if not expired)
        2. Room default from voice_room_defaults DB table
        3. "household"
    """

    def __init__(self, pool, ttl_minutes: int = 30):
        self._pool = pool
        self._ttl = timedelta(minutes=ttl_minutes)
        self._sessions: dict[str, RoomSession] = {}

    async def get_active_user(self, room_id: str) -> str:
        """Resolve the active user for a room.

        Checks in-memory session first (if not expired), then falls back
        to the DB room default, and finally to "household".
        """
        now = datetime.now()

        # Check for a valid in-memory session
        session = self._sessions.get(room_id)
        if session is not None and session.active_user is not None:
            if session.last_activity + self._ttl > now:
                return session.active_user
            # Session expired — remove it
            del self._sessions[room_id]

        # Fall back to DB room default
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT u.name
                    FROM voice_room_defaults vrd
                    JOIN users u ON vrd.default_user_id = u.id
                    WHERE vrd.room_id = $1
                    """,
                    room_id,
                )
                if row:
                    name: str = row["name"]
                    # Create a fresh session from the DB default
                    self._sessions[room_id] = RoomSession(
                        room_id=room_id,
                        active_user=name,
                        last_activity=now,
                    )
                    return name
        except Exception as e:
            import logging
            logging.getLogger("nova-core").warning(
                f"Failed to look up room default for {room_id!r}: {e}"
            )

        # Ultimate fallback
        return "household"

    async def set_active_user(self, room_id: str, user_name: str) -> None:
        """Set the active user for a room, updating the session timestamp."""
        self._sessions[room_id] = RoomSession(
            room_id=room_id,
            active_user=user_name,
            last_activity=datetime.now(),
        )

    def clear_expired(self) -> int:
        """Remove all expired sessions. Returns the count of removed sessions."""
        if len(self._sessions) == 0:
            return 0

        now = datetime.now()
        expired_rooms = [
            room_id
            for room_id, session in self._sessions.items()
            if session.last_activity + self._ttl <= now
        ]
        for room_id in expired_rooms:
            del self._sessions[room_id]
        return len(expired_rooms)
