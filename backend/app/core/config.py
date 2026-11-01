from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (or ../.env in local dev)."""

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = Field(min_length=32)
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 7

    cors_origins: str = "http://localhost:3000"  # comma-separated
    api_rate_limit: str = "100/minute"
    login_rate_limit: str = "5/minute"
    rate_limit_storage: str | None = None  # defaults to redis_url

    log_level: str = "INFO"

    scraper_user_agent: str = "RealEstateIntelligenceBot/0.1"
    cache_dir: str = ".cache"  # downloaded source files (backend/.cache in the dev container)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
