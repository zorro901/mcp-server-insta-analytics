"""FastMCP server definition with tool/resource/prompt registration."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from mcp_insta_analytics.cache import CacheBackend
from mcp_insta_analytics.config import Settings
from mcp_insta_analytics.fetcher import create_fetcher
from mcp_insta_analytics.rate_limiter import RateLimiterBackend

logger = logging.getLogger(__name__)

# Store references for resource access (set during lifespan)
_config_ref: Settings | None = None
_rate_limiter_ref: RateLimiterBackend | None = None
_auth_error_ref: str | None = None


# ---------------------------------------------------------------------------
# Lifespan — initializes shared deps, yields them as request_context
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[dict[str, object]]:
    """Initialize and tear down shared server dependencies."""
    global _config_ref, _rate_limiter_ref, _auth_error_ref

    config = Settings()

    cache: CacheBackend
    rate_limiter: RateLimiterBackend

    if config.storage_backend == "dynamodb":
        from mcp_insta_analytics.dynamodb_cache import DynamoDBCache
        from mcp_insta_analytics.dynamodb_rate_limiter import DynamoDBRateLimiter

        cache = DynamoDBCache(
            table_name=config.dynamodb_table_name,
            region=config.aws_region,
            endpoint_url=config.dynamodb_endpoint_url,
        )
        await cache.initialize()
        rate_limiter = DynamoDBRateLimiter(
            table_name=config.dynamodb_table_name,
            region=config.aws_region,
            endpoint_url=config.dynamodb_endpoint_url,
            max_per_minute=config.max_requests_per_minute,
            daily_budget=config.daily_request_budget,
            request_delay=config.request_delay,
        )
        await rate_limiter.initialize()
    else:
        from mcp_insta_analytics.cache import SqliteCache
        from mcp_insta_analytics.rate_limiter import SqliteRateLimiter

        cache = SqliteCache(config.cache_db_path)
        await cache.initialize()
        rl_path = str(cache.db_path.parent / "rate_limiter.db")  # type: ignore[union-attr]
        rate_limiter = SqliteRateLimiter(
            db_path=rl_path,
            max_per_minute=config.max_requests_per_minute,
            daily_budget=config.daily_request_budget,
            request_delay=config.request_delay,
        )
        await rate_limiter.initialize()

    # Fetcher — attempt initialization but allow degraded mode on auth failure
    fetcher = create_fetcher(config)
    auth_error: str | None = None
    if hasattr(fetcher, "initialize"):
        try:
            await fetcher.initialize()  # type: ignore[attr-defined]
        except Exception as exc:
            auth_error = str(exc)
            logger.warning(
                "Fetcher initialization failed (server will start in degraded mode): %s",
                auth_error,
            )

    if auth_error:
        logger.warning(
            "Instagram Analytics server started in DEGRADED mode (backend=%s)",
            config.fetcher_backend,
        )
    else:
        logger.info(
            "Instagram Analytics server started (backend=%s)", config.fetcher_backend
        )

    # Set references for resources
    _config_ref = config
    _rate_limiter_ref = rate_limiter
    _auth_error_ref = auth_error

    try:
        yield {
            "fetcher": fetcher,
            "cache": cache,
            "rate_limiter": rate_limiter,
            "config": config,
            "auth_error": auth_error,
        }
    finally:
        try:
            await fetcher.close()
        except Exception:
            pass
        await cache.close()
        await rate_limiter.close()
        logger.info("Instagram Analytics server stopped")


# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "Instagram Analytics",
    instructions="Read-only analytics server for Instagram posts. "
    "Provides engagement metrics, sentiment analysis, hashtag tracking, and more.",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Register MCP tools
# ---------------------------------------------------------------------------

from mcp_insta_analytics.tools.post_metrics import (  # noqa: E402
    compare_post_performance,
    get_post_metrics,
)
from mcp_insta_analytics.tools.search import (  # noqa: E402
    search_posts_by_hashtag,
    track_hashtag_trend,
)
from mcp_insta_analytics.tools.user_analytics import (  # noqa: E402
    analyze_best_posting_times,
    get_engagement_timeseries,
    get_user_profile_analytics,
    get_user_timeline_metrics,
)
from mcp_insta_analytics.tools.comments import (  # noqa: E402
    analyze_comment_sentiment,
    get_post_comments,
)

# Post metrics
mcp.tool(
    name="get_post_metrics",
    description="Get detailed metrics for a specific Instagram post, "
    "including engagement rate and like/comment ratio.",
)(get_post_metrics)

mcp.tool(
    name="compare_post_performance",
    description="Compare performance of multiple Instagram posts (2-20). "
    "Returns ranking, averages, and statistics.",
)(compare_post_performance)

# Search
mcp.tool(
    name="search_posts_by_hashtag",
    description="Search Instagram posts by hashtag. "
    "Returns results with engagement metrics.",
)(search_posts_by_hashtag)

mcp.tool(
    name="track_hashtag_trend",
    description="Track hashtag performance: volume, engagement, top posts, "
    "co-occurring tags, and trend direction.",
)(track_hashtag_trend)

# User analytics
mcp.tool(
    name="get_user_profile_analytics",
    description="Get user profile analytics including follower metrics "
    "and posting frequency.",
)(get_user_profile_analytics)

mcp.tool(
    name="get_user_timeline_metrics",
    description="Get a user's recent posts with engagement metrics and summary statistics.",
)(get_user_timeline_metrics)

mcp.tool(
    name="get_engagement_timeseries",
    description="Build engagement time series for a user's posts. "
    "Shows metrics over time with trend analysis.",
)(get_engagement_timeseries)

mcp.tool(
    name="analyze_best_posting_times",
    description="Analyze optimal posting times based on historical engagement data. "
    "Returns a day-of-week x hour heatmap.",
)(analyze_best_posting_times)

# Comments
mcp.tool(
    name="get_post_comments",
    description="Get comments for a specific Instagram post.",
)(get_post_comments)

mcp.tool(
    name="analyze_comment_sentiment",
    description="Analyze sentiment of comments on a post. Returns positive/negative/neutral "
    "distribution, overall score, and notable comments.",
)(analyze_comment_sentiment)


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------


@mcp.resource("insta-analytics://config/status")
async def resource_config_status() -> str:
    """Server configuration and connection status."""
    if _config_ref is None:
        return json.dumps({"status": "not_initialized"})
    result: dict[str, object] = {
        "status": "degraded" if _auth_error_ref else "running",
        "fetcher_backend": _config_ref.fetcher_backend,
        "cache_db_path": _config_ref.cache_db_path,
        "sentiment_engine": _config_ref.sentiment_engine,
        "max_requests_per_minute": _config_ref.max_requests_per_minute,
        "daily_request_budget": _config_ref.daily_request_budget,
    }
    if _auth_error_ref:
        result["auth_error"] = _auth_error_ref
    return json.dumps(result)


@mcp.resource("insta-analytics://usage/current")
async def resource_usage_current() -> str:
    """Current API usage statistics and remaining budget."""
    if _rate_limiter_ref is None:
        return json.dumps({"status": "not_initialized"})
    usage = await _rate_limiter_ref.get_usage()
    return json.dumps(usage.model_dump())


# ---------------------------------------------------------------------------
# MCP Prompts
# ---------------------------------------------------------------------------


@mcp.prompt()
def account_audit(username: str) -> str:
    """Comprehensive Instagram account health audit workflow."""
    return (
        f"Please perform a comprehensive audit of the Instagram account @{username}. "
        "Follow these steps:\n\n"
        f"1. Use get_user_profile_analytics for @{username} to get basic account metrics\n"
        f"2. Use get_user_timeline_metrics for @{username} (max_results=50) "
        "to analyze recent post performance\n"
        f"3. Use analyze_best_posting_times for @{username} to identify optimal posting windows\n"
        f"4. Use get_engagement_timeseries for @{username} (days_back=30) "
        "to see engagement trends\n\n"
        "Based on the data, provide:\n"
        "- Account health summary (followers, posting frequency, engagement rates)\n"
        "- Content performance analysis (best/worst performing posts)\n"
        "- Optimal posting schedule recommendations\n"
        "- Engagement trend analysis and actionable suggestions"
    )


@mcp.prompt()
def post_deep_dive(shortcode: str) -> str:
    """Deep analysis workflow for a specific Instagram post."""
    return (
        f"Please perform a deep dive analysis on Instagram post {shortcode}. "
        "Follow these steps:\n\n"
        f"1. Use get_post_metrics for post {shortcode} to get detailed engagement data\n"
        f"2. Use get_post_comments for post {shortcode} to see user comments\n"
        f"3. Use analyze_comment_sentiment for post {shortcode} to understand audience reaction\n\n"
        "Based on the data, provide:\n"
        "- Performance summary (engagement rate, likes, comments)\n"
        "- Comment analysis (themes, notable replies)\n"
        "- Sentiment breakdown with notable positive/negative responses"
    )


@mcp.prompt()
def hashtag_report(hashtag: str, days_back: int = 7) -> str:
    """Comprehensive hashtag performance report."""
    tag = hashtag if hashtag.startswith("#") else f"#{hashtag}"
    return (
        f"Please generate a comprehensive report for the hashtag {tag}. "
        "Follow these steps:\n\n"
        f"1. Use track_hashtag_trend for '{tag}' (days_back={days_back}) "
        "to get overall performance data\n"
        f"2. Use search_posts_by_hashtag with hashtag '{tag}' (max_results=50) "
        "to find top posts\n\n"
        "Based on the data, provide:\n"
        "- Hashtag overview (total volume, trend direction)\n"
        "- Engagement analysis (average metrics, top performing posts)\n"
        "- Co-occurring hashtags and content themes\n"
        "- Recommendations for using this hashtag effectively"
    )
