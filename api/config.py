from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PAYPAL_BASE_URLS = {
    "sandbox": "https://api-m.sandbox.paypal.com",
    "live": "https://api-m.paypal.com",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    cors_origins: list[str] = ["http://localhost:5173"]
    cookie_name: str = "kweli_session"
    cookie_secure: bool = True
    session_ttl_hours: int = 12
    max_body_bytes: int = 64 * 1024
    max_upload_bytes: int = 10 * 1024 * 1024

    paypal_env: Literal["sandbox", "live"] = "sandbox"
    paypal_client_id: str = ""
    paypal_client_secret: SecretStr = SecretStr("")
    paypal_webhook_id: str = ""

    anthropic_api_key: SecretStr | None = None
    llm_model: str = "claude-sonnet-5-5"

    vault_master_key: SecretStr | None = None

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, url: str) -> str:
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url

    @field_validator("cors_origins")
    @classmethod
    def reject_wildcard(cls, origins: list[str]) -> list[str]:
        if "*" in origins:
            raise ValueError("CORS origins must be explicit when credentials are allowed")
        return origins

    @property
    def paypal_base_url(self) -> str:
        return PAYPAL_BASE_URLS[self.paypal_env]


@lru_cache
def get_settings() -> Settings:
    return Settings()
