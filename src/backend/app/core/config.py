from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 数据库配置
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=5, ge=0)

    # 高德地图配置
    amap_timeout_seconds: float = Field(default=4, gt=0)
    amap_connect_timeout_seconds: float = Field(default=2, gt=0)
    amap_pool_timeout_seconds: float = Field(default=1, gt=0)
    amap_operation_timeout_seconds: float = Field(default=10, gt=0)
    amap_request_concurrency: int = Field(default=3, ge=1)
    amap_request_interval_seconds: float = Field(default=0.5, ge=0)
    amap_cache_ttl_seconds: int = Field(default=600, ge=1)
    amap_empty_cache_ttl_seconds: int = Field(default=30, ge=1)

    # LLM 配置
    llm_timeout_seconds: float = Field(default=10, gt=0, le=300, allow_inf_nan=False)
    llm_max_retries: int = Field(default=1, ge=0)
    llm_temperature: float = Field(default=0, ge=0, le=2)

    # 推荐配置
    decision_candidate_limit: int = Field(default=10, ge=1)
    decision_search_limit: int = Field(default=8, ge=1)
    decision_recommendation_limit: int = Field(default=3, ge=1)
    decision_score_weights: dict[str, float] = {
        "distance_cost": 0.22,
        "budget_match": 0.18,
        "rating_quality": 0.14,
        "novelty": 0.05,
        "data_completeness": 0.07,
    }
    decision_base_score_weight: float = Field(default=0.8, ge=0, le=1)
    decision_request_match_weight: float = Field(default=0.2, ge=0, le=1)
    decision_timeout_seconds: float = Field(default=20, gt=0, le=600, allow_inf_nan=False)

    # 偏好学习配置
    preference_learning_min_meals: int = Field(default=10, ge=1)
    preference_learning_interval: int = Field(default=5, ge=1)
    preference_learning_sample_limit: int = Field(default=20, ge=1)
    preference_learning_min_evidence: int = Field(default=3, ge=1)

    # 任务队列配置
    task_lease_seconds: int = Field(default=60, ge=3, le=3600)
    task_poll_seconds: float = Field(default=1, ge=0.1, le=60, allow_inf_nan=False)
    task_queue_timeout_seconds: float = Field(default=60, ge=1, le=3600, allow_inf_nan=False)
    task_concurrency: int = Field(default=8, ge=1)
    task_max_active: int = Field(default=16, ge=1)
    task_user_submissions_per_minute: int = Field(default=5, ge=1)

    # 用户认证配置
    auth_session_days: int = Field(default=30, ge=1)
    auth_register_limit: int = Field(default=10, ge=1)
    auth_register_window_seconds: int = Field(default=3600, ge=1)
    auth_login_ip_limit: int = Field(default=30, ge=1)
    auth_login_user_limit: int = Field(default=10, ge=1)
    auth_login_window_seconds: int = Field(default=900, ge=1)
    auth_change_password_limit: int = Field(default=10, ge=1)
    auth_change_password_window_seconds: int = Field(default=900, ge=1)
    auth_password_concurrency: int = Field(default=1, ge=1)
    auth_password_max_waiters: int = Field(default=2, ge=0)
    auth_password_wait_seconds: float = Field(default=1, gt=0, allow_inf_nan=False)

    # SSE 配置
    sse_max_connections_per_user: int = Field(default=2, ge=1)
    sse_max_connections: int = Field(default=32, ge=1)


settings = Settings()
