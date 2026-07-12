"""Database helper module using asyncpg."""
from __future__ import annotations

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


def _run_alembic_upgrade():
    alembic_cfg = Config("services/nova-core/alembic.ini")
    command.upgrade(alembic_cfg, "head")


async def run_migrations():
    _run_alembic_upgrade()

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_inbound_at TIMESTAMP WITH TIME ZONE"
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_emails (
                email_id VARCHAR(255) PRIMARY KEY,
                processed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

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

