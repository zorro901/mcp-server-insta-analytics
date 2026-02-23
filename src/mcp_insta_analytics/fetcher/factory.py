"""Factory function for creating data fetcher instances."""

from __future__ import annotations

from mcp_insta_analytics.config import Settings
from mcp_insta_analytics.errors import ConfigError

from .base import AbstractFetcher


def create_fetcher(config: Settings) -> AbstractFetcher:
    """Create a fetcher instance based on the configured backend."""
    match config.fetcher_backend:
        case "instaloader":
            from .instaloader_fetcher import InstaLoaderFetcher

            return InstaLoaderFetcher(config)
        case _:
            raise ConfigError(f"Unknown fetcher backend: {config.fetcher_backend}")
