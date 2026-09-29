from __future__ import annotations

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: SecretStr
    amap_web_service_key: SecretStr
    llm_api_key: SecretStr
    llm_base_url: str
    llm_model: str
    cors_origins: str = "http://localhost:5173"
    amap_timeout_seconds: float = 4
    amap_route_concurrency: int = 3
    amap_cache_ttl_seconds: int = 600
    amap_route_cache_ttl_seconds: int = 300
    llm_timeout_seconds: float = 10
    decision_timeout_seconds: float = 20
    task_lease_seconds: int = 60
    task_poll_seconds: float = 1
    auth_cookie_secure: bool = True
    app_env: str = "production"

    @field_validator("app_env")
    @classmethod
    def environment(cls, value: str) -> str:
        if value not in {"local", "production"}:
            raise ValueError("APP_ENV must be local or production")
        return value

    @model_validator(mode="after")
    def cookie_security(self) -> Settings:
        if self.app_env == "production" and not self.auth_cookie_secure:
            raise ValueError("Secure auth cookies are required in production")
        return self

    @field_validator(
        "database_url",
        "amap_web_service_key",
        "llm_api_key",
        "llm_base_url",
        "llm_model",
    )
    @classmethod
    def required_config(cls, value: str | SecretStr) -> str | SecretStr:
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not raw.strip() or raw.startswith(("replace-", "your-")):
            raise ValueError("Required configuration is missing or is a placeholder")
        return value

    @property
    def db_url(self) -> str:
        return self.database_url.get_secret_value()
