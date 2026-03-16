"""MCP tools for searching posts by hashtag."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastmcp import Context

from mcp_insta_analytics.analysis.metrics import calculate_engagement_metrics
from mcp_insta_analytics.analysis.timeseries import build_timeseries
from mcp_insta_analytics.models import (
    HashtagPerformanceResult,
    Post,
    PostWithMetrics,
    SearchResult,
    post_with_metrics,
)
from mcp_insta_analytics.tools import extract_deps

logger = logging.getLogger(__name__)


async def search_posts_by_hashtag(
    hashtag: str,
    max_results: int = 12,
    sort_order: str = "relevancy",
    *,
    ctx: Context,
) -> SearchResult:
    """Search for posts by hashtag and return them with engagement metrics."""
    deps = extract_deps(ctx)

    tag = hashtag.lstrip("#")
    await deps.rate_limiter.acquire()
    posts = await deps.fetcher.get_hashtag_posts(tag, count=max_results)

    results: list[PostWithMetrics] = []
    for post in posts:
        metrics = calculate_engagement_metrics(post)
        results.append(post_with_metrics(post, metrics))

    sort_fields = {"engagement_rate", "like_count", "comment_count"}
    if sort_order in sort_fields:
        results.sort(key=lambda r: getattr(r, sort_order), reverse=True)

    return SearchResult(
        hashtag=f"#{tag}",
        total_results=len(results),
        posts=results,
    )


def _filter_posts_by_days(posts: list[Post], days_back: int) -> list[Post]:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days_back)
    return [p for p in posts if p.created_at is not None and p.created_at >= cutoff]


async def track_hashtag_trend(
    hashtag: str,
    ctx: Context,
    days_back: int = 7,
    sample_size: int = 15,
) -> HashtagPerformanceResult:
    """Track the performance of a hashtag over a recent time window."""
    deps = extract_deps(ctx)

    tag = hashtag.lstrip("#")
    await deps.rate_limiter.acquire()
    posts = await deps.fetcher.get_hashtag_posts(tag, count=sample_size)
    posts = _filter_posts_by_days(posts, days_back)

    if not posts:
        return HashtagPerformanceResult(
            hashtag=f"#{tag}",
            days_back=days_back,
            total_posts=0,
            average_engagement=0.0,
            top_posts=[],
            co_occurring_hashtags=[],
            timeseries=None,
        )

    from collections import Counter

    post_metrics_pairs = [(p, calculate_engagement_metrics(p)) for p in posts]
    avg_engagement = sum(m.engagement_rate for _, m in post_metrics_pairs) / len(
        post_metrics_pairs
    )

    sorted_pairs = sorted(
        post_metrics_pairs, key=lambda pair: pair[1].engagement_rate, reverse=True
    )
    top_posts = [post_with_metrics(p, m) for p, m in sorted_pairs[:5]]

    co_occurring: Counter[str] = Counter()
    for post in posts:
        for t in post.hashtags:
            normalised = t.lower()
            if normalised != tag.lower():
                co_occurring[normalised] += 1

    timeseries = build_timeseries(posts, metric="like_count", granularity="day")

    return HashtagPerformanceResult(
        hashtag=f"#{tag}",
        days_back=days_back,
        total_posts=len(posts),
        average_engagement=avg_engagement,
        top_posts=top_posts,
        co_occurring_hashtags=co_occurring.most_common(20),
        timeseries=timeseries,
    )
