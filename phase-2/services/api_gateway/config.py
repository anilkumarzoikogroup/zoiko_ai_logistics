"""Typed settings for the Phase 2 API Gateway, loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    db_url: str = "postgresql://postgres:1234@localhost/zoiko"

    # Auth
    zoiko_dev_mode: bool = False
    zoiko_dev_secret: str = "zoiko-dev-secret-for-testing-only"
    zoiko_issuer: str = "https://auth.zoikotech.com"
    zoiko_admin_password: str = "Admin@1234"

    # Kafka
    kafka_bootstrap: str = ""

    # OPA
    opa_url: str = ""

    # CORS
    zoiko_cors_origins: str = "http://localhost:5173"

    # Feature flags
    zoiko_ff_sc_001_enabled: str = "*"

    # Rate limiting
    zoiko_rate_limit_enabled: bool = False

    # Token TTL
    token_ttl_minutes: int = 15

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
