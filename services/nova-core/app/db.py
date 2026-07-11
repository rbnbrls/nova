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

