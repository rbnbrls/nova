"""Runtime configuration, loaded from environment (see .env.example)."""
from __future__ import annotations

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
