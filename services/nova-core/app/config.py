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

    # LLM (Ollama)
    ollama_base_url: str = "http://ollama:11434"
    nova_model: str = "qwen3:14b"
    nova_embed_model: str = "nomic-embed-text"

    # Database
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "nova"
    postgres_user: str = "nova"
    postgres_password: str = ""

    # Calendar (CalDAV)
    caldav_url: str = "http://radicale:5232/"


    # MS Graph Email Configuration
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""
    azure_mailbox_email: str = ""

    # Household identity: "number:name,number:name"
    nova_whatsapp_users: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = ""



    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
