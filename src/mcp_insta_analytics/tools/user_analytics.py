"""MCP tools for Instagram user profile and timeline analytics."""

from __future__ import annotations

import json
import logging

from fastmcp import Context

from mcp_insta_analytics.analysis.metrics import calculate_engagement_metrics
from mcp_insta_analytics.analysis.timeseries import build_posting_time_heatmap, build_timeseries
from mcp_insta_analytics.errors import InstaAnalyticsError
from mcp_insta_analytics.models import (
    BestPostingTimesResult,
    EngagementTimeseriesResult,
    PostAndMetrics,
    TimelineSummary,
    UserProfileAnalytics,
    UserTimelineResult,
    user_profile_analytics,
)
from mcp_insta_analytics.tools import extract_deps

logger = logging.getLogger(__name__)


async def get_user_profile_analytics(username: str, ctx: Context) -> UserProfileAnalytics:
    """Fetch a user's profile and return analytics including derived metrics."""
    deps = extract_deps(ctx)

    cache_key = f"user:{username}"
    try:
        cached = await deps.cache.get(cache_key)
        if cached is not None:
            return UserProfileAnalytics(**json.loads(cached))

        await deps.rate_limiter.acquire()
        profile = await deps.fetcher.get_user_profile(username)
        result = user_profile_analytics(profile)

        await deps.cache.set(
            cache_key,
            json.dumps(result.model_dump(mode="json"), default=str),
            ttl=deps.config.cache_ttl_profiles,
        )
        return result

    except InstaAnalyticsError:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in get_user_profile_analytics")
        raise InstaAnalyticsError(
            f"Failed to fetch profile analytics for @{username}: {exc}",
        ) from exc


async def get_user_timeline_metrics(
    username: str,
    max_results: int = 20,
    ctx: Context = None,  # type: ignore[assignment]
) -> UserTimelineResult:
    """Fetch recent posts and compute per-post engagement metrics plus summary."""
    deps = extract_deps(ctx)

    try:
        await deps.rate_limiter.acquire()
        posts = await deps.fetcher.get_user_posts(username, max_results)

        post_metrics: list[PostAndMetrics] = []
        for post in posts:
            metrics = calculate_engagement_metrics(post)
            post_metrics.append(PostAndMetrics(post=post, metrics=metrics))

        if post_metrics:
            engagement_rates = [p.metrics.engagement_rate for p in post_metrics]
            total_engagements_list = [p.metrics.total_engagements for p in post_metrics]
            avg_engagement_rate = sum(engagement_rates) / len(engagement_rates)
            total_engagements = sum(total_engagements_list)
            most_idx = engagement_rates.index(max(engagement_rates))
            least_idx = engagement_rates.index(min(engagement_rates))
            summary = TimelineSummary(
                avg_engagement_rate=avg_engagement_rate,
                total_engagements=total_engagements,
                post_count=len(post_metrics),
                most_engaging_post=post_metrics[most_idx],
                least_engaging_post=post_metrics[least_idx],
            )
        else:
            summary = TimelineSummary(
                avg_engagement_rate=0.0,
                total_engagements=0,
                post_count=0,
                most_engaging_post=None,
                least_engaging_post=None,
            )

        return UserTimelineResult(username=username, posts=post_metrics, summary=summary)

    except InstaAnalyticsError:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in get_user_timeline_metrics")
        raise InstaAnalyticsError(
            f"Failed to fetch timeline metrics for @{username}: {exc}",
        ) from exc


async def get_engagement_timeseries(
    username: str,
    ctx: Context,
    metrics: list[str] | None = None,
    granularity: str = "day",
    days_back: int = 14,
) -> EngagementTimeseriesResult:
    """Build engagement timeseries for a user's recent posts."""
    if metrics is None:
        metrics = ["like_count", "engagement_rate"]

    deps = extract_deps(ctx)
    from datetime import datetime, timedelta, timezone

    fetch_count = min(max(12, days_back * 2), 50)
    await deps.rate_limiter.acquire()
    posts = await deps.fetcher.get_user_posts(username, count=fetch_count)

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days_back)
    posts = [p for p in posts if p.created_at is not None and p.created_at >= cutoff]

    timeseries_results = [
        build_timeseries(posts, metric=metric, granularity=granularity) for metric in metrics
    ]

    return EngagementTimeseriesResult(
        username=username,
        granularity=granularity,
        days_back=days_back,
        timeseries=timeseries_results,
    )


async def analyze_best_posting_times(
    username: str,
    ctx: Context,
    metric: str = "engagement_rate",
    sample_size: int = 50,
    timezone: str = "Asia/Tokyo",
) -> BestPostingTimesResult:
    """Analyse the best posting times for a user based on historical engagement."""
    deps = extract_deps(ctx)

    await deps.rate_limiter.acquire()
    posts = await deps.fetcher.get_user_posts(username, count=sample_size)

    heatmap = build_posting_time_heatmap(posts, metric=metric, timezone_str=timezone)

    actual_sample = heatmap.sample_size
    if actual_sample >= 100:
        confidence = "high"
    elif actual_sample >= 50:
        confidence = "medium"
    elif actual_sample >= 20:
        confidence = "low"
    else:
        confidence = "very low"

    confidence_note = (
        f"Analysis based on {actual_sample} posts. "
        f"Confidence: {confidence}. "
        f"{'Results are statistically reliable.' if confidence == 'high' else 'Collect more data for more reliable results.'}"
    )

    return BestPostingTimesResult(
        username=username,
        timezone=timezone,
        metric=metric,
        heatmap=heatmap.heatmap,
        best_windows=heatmap.best_windows,
        sample_size=actual_sample,
        confidence_note=confidence_note,
    )
