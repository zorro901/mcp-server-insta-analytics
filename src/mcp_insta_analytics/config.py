"""Configuration management using pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="INSTA_ANALYTICS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Instagram authentication (optional — public profiles work without login)
    username: str = ""
    password: str = ""

    # Fetcher backend
    fetcher_backend: str = "instaloader"

    # Request delay between API calls (seconds)
    request_delay: float = 4.0

    # Cache settings
    cache_db_path: str = "~/.cache/mcp-insta-analytics/cache.db"
    cache_ttl_posts: int = 900  # 15 minutes
    cache_ttl_profiles: int = 86400  # 24 hours
    cache_ttl_search: int = 600  # 10 minutes

    # Rate limiting
    max_requests_per_minute: int = 15
    daily_request_budget: int = 500

    # Sentiment analysis
    sentiment_engine: str = "vader"

    # Storage backend
    storage_backend: str = "sqlite"

    # Server transport
    server_host: str = "0.0.0.0"
    server_port: int = 8001
