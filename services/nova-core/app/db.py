"""Database helper module using asyncpg."""
from __future__ import annotations

import asyncpg

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


async def run_migrations():
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
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                whatsapp_number TEXT UNIQUE,
                dnd_enabled BOOLEAN DEFAULT FALSE,
                dnd_start TIME DEFAULT '22:00:00',
                dnd_end TIME DEFAULT '07:00:00',
                morning_briefing_enabled BOOLEAN DEFAULT TRUE,
                morning_briefing_time TIME DEFAULT '07:00:00',
                weekly_briefing_enabled BOOLEAN DEFAULT TRUE,
                weekly_briefing_day INTEGER DEFAULT 1,
                weekly_briefing_time TIME DEFAULT '09:00:00',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS whatsapp_verification_codes (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                whatsapp_number TEXT NOT NULL,
                code TEXT NOT NULL,
                attempts INTEGER DEFAULT 0,
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
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

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS queued_notifications (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                whatsapp_number TEXT NOT NULL,
                message_text TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )



