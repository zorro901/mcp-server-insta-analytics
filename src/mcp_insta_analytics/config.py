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
    session_cookie: str = ""  # Browser sessionid cookie

    # Fetcher backend
    fetcher_backend: str = "instaloader"

    # Request delay between API calls (seconds).
    # Instagram aggressively rate-limits GraphQL requests; values below 5s
    # frequently trigger 403 responses.
    request_delay: float = 6.0

    # Cache settings
    cache_db_path: str = "~/.cache/mcp-insta-analytics/cache.db"
    cache_ttl_posts: int = 1800  # 30 minutes
    cache_ttl_profiles: int = 86400  # 24 hours
    cache_ttl_search: int = 1800  # 30 minutes

    # Rate limiting
    max_requests_per_minute: int = 6
    daily_request_budget: int = 200

    # Sentiment analysis
    sentiment_engine: str = "vader"

    # Storage backend: "sqlite" (Docker/local) or "dynamodb" (Lambda)
    storage_backend: str = "sqlite"
    dynamodb_table_name: str = "mcp-insta-analytics"
    aws_region: str = "ap-northeast-1"
    dynamodb_endpoint_url: str = ""  # ローカルDynamoDB用

    # Lambda Function URL access protection (Bearer token)
    api_key: str = ""

    # Server transport
    server_host: str = "0.0.0.0"
    server_port: int = 8001
