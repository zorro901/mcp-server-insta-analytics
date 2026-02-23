"""MCP tools for fetching and comparing post metrics."""

from __future__ import annotations

import json
import logging

from fastmcp import Context

from mcp_insta_analytics.analysis.metrics import calculate_engagement_metrics, rank_posts
from mcp_insta_analytics.cache import CacheBackend
from mcp_insta_analytics.config import Settings
from mcp_insta_analytics.fetcher.base import AbstractFetcher
from mcp_insta_analytics.models import (
    EngagementMetrics,
    MetricStatistics,
    Post,
    PostComparisonError,
    PostComparisonResult,
    PostWithMetrics,
    post_with_metrics,
)
from mcp_insta_analytics.rate_limiter import RateLimiterBackend
from mcp_insta_analytics.tools import extract_deps

logger = logging.getLogger(__name__)


async def _fetch_post_with_cache(
    shortcode: str,
    fetcher: AbstractFetcher,
    cache: CacheBackend,
    rate_limiter: RateLimiterBackend,
    config: Settings,
) -> Post:
    cache_key = f"post:{shortcode}"
    cached = await cache.get(cache_key)
    if cached is not None:
        logger.debug("Cache hit for %s", cache_key)
        return Post(**json.loads(cached))
    logger.debug("Cache miss for %s, fetching from API", cache_key)
    await rate_limiter.acquire()
    post = await fetcher.get_post_detail(shortcode)
    await cache.set(
        cache_key,
        json.dumps(post.model_dump(mode="json")),
        ttl=config.cache_ttl_posts,
    )
    return post


async def get_post_metrics(shortcode: str, ctx: Context) -> PostWithMetrics:
    """Fetch a single post and return its data together with engagement metrics."""
    deps = extract_deps(ctx)
    post = await _fetch_post_with_cache(
        shortcode, deps.fetcher, deps.cache, deps.rate_limiter, deps.config
    )
    metrics = calculate_engagement_metrics(post)
    return post_with_metrics(post, metrics)


async def compare_post_performance(
    shortcodes: list[str],
    rank_by: str,
    ctx: Context,
) -> PostComparisonResult | PostComparisonError:
    """Compare performance of multiple posts ranked by a chosen metric."""
    if len(shortcodes) < 2 or len(shortcodes) > 20:
        return PostComparisonError(
            error="InvalidInput",
            message="shortcodes must contain between 2 and 20 items.",
        )

    deps = extract_deps(ctx)
    posts: list[Post] = []
    for sc in shortcodes:
        post = await _fetch_post_with_cache(
            sc, deps.fetcher, deps.cache, deps.rate_limiter, deps.config
        )
        posts.append(post)

    ranked_pairs = rank_posts(posts, metric=rank_by)
    ranked_posts = [post_with_metrics(p, m) for p, m in ranked_pairs]

    metric_fields = ["engagement_rate", "like_comment_ratio", "total_engagements"]
    all_metrics: list[EngagementMetrics] = [m for _, m in ranked_pairs]

    statistics: dict[str, MetricStatistics] = {}
    for field in metric_fields:
        values: list[float] = [float(getattr(m, field)) for m in all_metrics]
        statistics[field] = MetricStatistics(
            average=sum(values) / len(values),
            max=max(values),
            min=min(values),
        )

    return PostComparisonResult(ranked_posts=ranked_posts, statistics=statistics)
