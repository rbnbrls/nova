"""Database helper module using asyncpg."""
from __future__ import annotations
import os

import asyncpg

from alembic import command
from alembic.config import Config

from .config import settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn=settings.database_url)
    return _pool


async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def get_user_memories(user_name: str) -> str:
    """Return formatted memories for a user: their private + all household-scope memories."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        user_id = await conn.fetchval("SELECT id FROM users WHERE name = $1", user_name)
        if not user_id:
            return ""
        rows = await conn.fetch(
            """
            SELECT content, scope FROM memories
            WHERE (user_id = $1 AND scope = 'private') OR scope = 'household'
            ORDER BY created_at DESC LIMIT 20
            """,
            user_id
        )
    if not rows:
        return ""
    lines = [f"- {r['content']} [{r['scope']}]" for r in rows]
    return "\n".join(lines)


def _run_alembic_upgrade():
    _dir = os.path.dirname(os.path.abspath(__file__))
    alembic_cfg = Config(os.path.join(_dir, "..", "alembic.ini"))
    command.upgrade(alembic_cfg, "head")


async def run_migrations():
    pool = await get_pool()
    async with pool.acquire() as conn:
        has_alembic = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'alembic_version')"
        )
        if not has_alembic:
            async def has_table(t: str) -> bool:
                return await conn.fetchval(
                    f"SELECT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = '{t}')"
                )
            
            async def has_column(t: str, c: str) -> bool:
                return await conn.fetchval(
                    f"""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='{t}' AND column_name='{c}'
                    )
                    """
                )
            
            if await has_table("users"):
                version = "0001"
                if await has_table("processed_emails"):
                    version = "0003"
                if await has_table("audit_log"):
                    version = "0004"
                if await has_table("voice_room_defaults"):
                    version = "0005"
                if await has_column("memories", "scope"):
                    version = "0006"
                if await has_table("grocery_items"):
                    version = "0008"
                if await has_column("tasks", "recurrence_pattern"):
                    version = "0010"
                if not await has_table("processed_emails"):
                    version = "0011"
                
                import logging
                logging.getLogger("nova-core").warning(
                    f"Alembic tracking missing but tables exist. Stamping DB to version: {version}"
                )
                
                _dir = os.path.dirname(os.path.abspath(__file__))
                alembic_cfg = Config(os.path.join(_dir, "..", "alembic.ini"))
                command.stamp(alembic_cfg, version)

    _run_alembic_upgrade()

    async with pool.acquire() as conn:
        if settings.nova_whatsapp_users:
            for entry in settings.nova_whatsapp_users.split(","):
                entry = entry.strip()
                if not entry or ":" not in entry:
                    continue
                number, name = entry.split(":", 1)
                number = number.strip().lstrip("+")
                name = name.strip()
                user_id = await conn.fetchval("SELECT id FROM users WHERE name = $1", name)
                if user_id:
                    pref_exists = await conn.fetchval(
                        "SELECT 1 FROM user_preferences WHERE user_id = $1", user_id
                    )
                    if not pref_exists:
                        await conn.execute(
                            """
                            INSERT INTO user_preferences (user_id, whatsapp_number)
                            VALUES ($1, $2)
                            ON CONFLICT (whatsapp_number) DO NOTHING
                            """,
                            user_id,
                            number
                        )
                        # Mirror WhatsApp number into channel_identities for unified resolution
                        await conn.execute(
                            """
                            INSERT INTO channel_identities (user_id, channel, channel_id)
                            VALUES ($1, 'whatsapp', $2)
                            ON CONFLICT (channel, channel_id) DO NOTHING
                            """,
                            user_id,
                            number
                        )

        if settings.nova_telegram_users:
            for entry in settings.nova_telegram_users.split(","):
                entry = entry.strip()
                if not entry or ":" not in entry:
                    continue
                chat_id, name = entry.split(":", 1)
                chat_id = chat_id.strip()
                name = name.strip()
                user_id = await conn.fetchval("SELECT id FROM users WHERE name = $1", name)
                if user_id:
                    exists = await conn.fetchval(
                        "SELECT 1 FROM channel_identities WHERE channel = 'telegram' AND channel_id = $1",
                        chat_id
                    )
                    if not exists:
                        await conn.execute(
                            """
                            INSERT INTO channel_identities (user_id, channel, channel_id)
                            VALUES ($1, 'telegram', $2)
                            ON CONFLICT (channel, channel_id) DO NOTHING
                            """,
                            user_id,
                            chat_id
                        )

        if settings.nova_voice_room_defaults:
            import re as _room_re
            for entry in settings.nova_voice_room_defaults.split(","):
                entry = entry.strip()
                if not entry or ":" not in entry:
                    continue
                room_id, name = entry.split(":", 1)
                room_id = room_id.strip()
                name = name.strip()
                # Validate room_id: non-empty alphanumeric + underscore
                if not room_id or not _room_re.match(r"^[a-zA-Z0-9_]+$", room_id):
                    import logging
                    logging.getLogger("nova-core").warning(
                        f"Skipping malformed voice room entry: room_id={room_id!r}"
                    )
                    continue
                user_id = await conn.fetchval("SELECT id FROM users WHERE name = $1", name)
                if not user_id:
                    import logging
                    logging.getLogger("nova-core").warning(
                        f"Skipping voice room entry {room_id}:{name} — user not found"
                    )
                    continue
                await conn.execute(
                    """
                    INSERT INTO voice_room_defaults (room_id, default_user_id)
                    VALUES ($1, $2)
                    ON CONFLICT (room_id) DO UPDATE SET
                        default_user_id = EXCLUDED.default_user_id,
                        updated_at = now()
                    """,
                    room_id,
                    user_id
                )

