"""Runtime configuration, loaded from environment (see .env.example)."""
from __future__ import annotations

import logging

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Core
    nova_env: str = "development"
    nova_log_level: str = "INFO"
    nova_timezone: str = "Europe/Amsterdam"
    nova_api_token: str = ""
    nova_max_iterations: int = 6
    # Per-turn wall-clock timeout in seconds (covers all iterations + retries)
    nova_max_turn_timeout: int = 120
    nova_tracing_enabled: bool = True

    # Tracing / slowness thresholds
    nova_slow_llm_ms: int = 15000   # LLM inference call exceeds this → slowness alert
    nova_slow_tool_ms: int = 5000   # Single tool execution exceeds this → slowness alert
    nova_slow_turn_ms: int = 30000  # Total agent turn exceeds this → slowness alert

    # LLM (Ollama)
    ollama_base_url: str = "http://ollama:11434"
    nova_model: str = "qwen3:14b"
    nova_embed_model: str = "nomic-embed-text"
    nova_vision_model: str = "llava"

    # Database
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "nova"
    postgres_user: str = "nova"
    postgres_password: str = ""

    # Calendar (CalDAV)
    caldav_url: str = "http://radicale:5232/"
    caldav_username: str = ""
    caldav_password: str = ""

    @property
    def carddav_base_url(self) -> str:
        """Radicale CardDAV endpoint for contact sync."""
        return self.caldav_url.rstrip("/")

    # Home Assistant
    nova_ha_token: str = ""
    nova_ha_url: str = "http://homeassistant:8123"

    # Email (IMAP + SMTP) — Phase 38
    nova_domain: str = ""          # No default — must be explicitly set
    nova_imap_host: str = ""
    nova_imap_port: int = 993      # IMAPS
    nova_imap_user: str = ""
    nova_imap_pass: str = ""
    nova_imap_use_ssl: bool = True
    nova_smtp_host: str = ""
    nova_smtp_port: int = 587      # STARTTLS
    nova_smtp_user: str = ""
    nova_smtp_pass: str = ""
    nova_smtp_use_tls: bool = True

    # Household identity: "number:name,number:name"
    nova_whatsapp_users: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    nova_telegram_enabled: bool = False
    nova_telegram_users: str = ""

    # Scheduled Maintenance Agent (Phase 29)
    forgejo_url: str = "https://git.7rb.nl"
    forgejo_repo: str = "ruben/nova"
    forgejo_token: str = ""
    maintenance_enabled: bool = True
    maintenance_dep_check_enabled: bool = True
    maintenance_log_anomaly_enabled: bool = True
    maintenance_backup_verify_enabled: bool = True
    maintenance_trend_report_enabled: bool = True
    backup_dump_dir: str = "/backups/postgres"
    backup_dump_pattern: str = "nova-*.sql"

    # Voice room defaults: comma-separated "room_name:UserName" pairs
    nova_voice_room_defaults: str = ""

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def nova_email(self) -> str:
        """Derived email identity: nova@{NOVA_DOMAIN} (per D-02)."""
        if not self.nova_domain:
            return ""
        return f"nova@{self.nova_domain}"


settings = Settings()

log = logging.getLogger("nova-core")


# --- Runtime-persistent config (Phase 41 — app_config DB table) ---
# Module-level cache; re-reads from DB on each call. Writes are infrequent
# and happen via the same process, so TTL is unnecessary.
# TODO: Extend with active_embed_model, active_vision_model in future phases.
_active_model_override: str | None = None


async def get_active_model() -> str:
    """Return active model from app_config, falling back to env default."""
    global _active_model_override
    if _active_model_override:
        return _active_model_override
    try:
        from . import db

        pool = await db.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM app_config WHERE key = 'active_model'"
            )
            if row and row["value"]:
                _active_model_override = row["value"]
                return row["value"]
    except Exception:
        log.warning("Failed to read active_model from DB, using env default")
    return settings.nova_model


async def set_active_model(model: str) -> None:
    """Persist active model to app_config (upsert)."""
    global _active_model_override
    from . import db

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO app_config (key, value) VALUES ('active_model', $1)
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, updated_at = now()
            """,
            model,
        )
    _active_model_override = model


def get_active_model_sync() -> str:
    """Synchronous getter for places that cannot use await.
    Falls back to env default if override hasn't been loaded yet."""
    return _active_model_override or settings.nova_model
