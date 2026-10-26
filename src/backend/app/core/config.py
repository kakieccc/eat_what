from __future__ import annotations

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: SecretStr
    amap_web_service_key: SecretStr
    llm_api_key: SecretStr
    llm_base_url: str
    llm_model: str
    cors_origins: str = "http://localhost:5173"
    amap_timeout_seconds: float = Field(default=4, gt=0)
    amap_connect_timeout_seconds: float = Field(default=2, gt=0)
    amap_pool_timeout_seconds: float = Field(default=1, gt=0)
    amap_operation_timeout_seconds: float = Field(default=10, gt=0)
    amap_request_concurrency: int = Field(default=3, ge=1)
    amap_request_interval_seconds: float = Field(default=0.5, ge=0)
    amap_cache_ttl_seconds: int = Field(default=600, ge=1)
    amap_empty_cache_ttl_seconds: int = Field(default=30, ge=1)
    llm_timeout_seconds: float = Field(default=10, gt=0, le=300, allow_inf_nan=False)
    llm_max_retries: int = Field(default=1, ge=0)
    llm_temperature: float = Field(default=0, ge=0, le=2)
    decision_timeout_seconds: float = Field(default=20, gt=0, le=600, allow_inf_nan=False)
    task_lease_seconds: int = Field(default=60, ge=3, le=3600)
    task_poll_seconds: float = Field(default=1, ge=0.1, le=60, allow_inf_nan=False)
    task_queue_timeout_seconds: float = Field(default=60, ge=1, le=3600, allow_inf_nan=False)
    auth_session_days: int = Field(default=30, ge=1)

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
