"""MCP tool implementations."""

from __future__ import annotations

from typing import NamedTuple

from fastmcp import Context

from mcp_insta_analytics.cache import CacheBackend
from mcp_insta_analytics.config import Settings
from mcp_insta_analytics.fetcher.base import AbstractFetcher
from mcp_insta_analytics.rate_limiter import RateLimiterBackend


class Deps(NamedTuple):
    """Shared dependencies extracted from the FastMCP request context."""

    fetcher: AbstractFetcher
    cache: CacheBackend
    rate_limiter: RateLimiterBackend
    config: Settings


def extract_deps(ctx: Context) -> Deps:
    """Unpack shared dependencies from the request context."""
    lc: dict[str, object] = ctx.lifespan_context  # type: ignore[assignment]
    return Deps(
        fetcher=lc["fetcher"],  # type: ignore[arg-type]
        cache=lc["cache"],  # type: ignore[arg-type]
        rate_limiter=lc["rate_limiter"],  # type: ignore[arg-type]
        config=lc["config"],  # type: ignore[arg-type]
    )
