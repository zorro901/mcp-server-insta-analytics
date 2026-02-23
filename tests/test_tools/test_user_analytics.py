"""Tests for user analytics tools."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from mcp_insta_analytics.models import Post, UserProfile
from mcp_insta_analytics.tools.user_analytics import (
    analyze_best_posting_times,
    get_engagement_timeseries,
    get_user_profile_analytics,
    get_user_timeline_metrics,
)


def _make_ctx(
    fetcher: AsyncMock,
    cache: AsyncMock | None = None,
    config: MagicMock | None = None,
) -> MagicMock:
    ctx = MagicMock()
    if cache is None:
        cache = AsyncMock()
        cache.get.return_value = None
    if config is None:
        config = MagicMock()
        config.cache_ttl_profiles = 600
    ctx.lifespan_context = {
        "fetcher": fetcher,
        "cache": cache,
        "rate_limiter": AsyncMock(),
        "config": config,
    }
    return ctx


def _make_user() -> UserProfile:
    return UserProfile(
        id="123",
        username="testuser",
        followers_count=5000,
        following_count=500,
        media_count=365,
        created_at=datetime(2020, 1, 15, tzinfo=timezone.utc),
    )


def _make_post(like_count: int = 100, created_at: datetime | None = None) -> Post:
    return Post(
        id="1",
        shortcode="abc",
        like_count=like_count,
        comment_count=10,
        created_at=created_at or datetime.now(tz=timezone.utc),
    )


class TestGetUserProfileAnalytics:
    async def test_returns_analytics(self):
        user = _make_user()
        fetcher = AsyncMock()
        fetcher.get_user_profile.return_value = user
        ctx = _make_ctx(fetcher)

        result = await get_user_profile_analytics("testuser", ctx)
        assert result.username == "testuser"
        assert result.followers_count == 5000
        assert result.follower_following_ratio == 10.0

    async def test_cache_hit(self):
        from mcp_insta_analytics.models import user_profile_analytics

        user = _make_user()
        analytics = user_profile_analytics(user)
        fetcher = AsyncMock()
        cache = AsyncMock()
        cache.get.return_value = json.dumps(analytics.model_dump(mode="json"), default=str)
        ctx = _make_ctx(fetcher, cache=cache)

        result = await get_user_profile_analytics("testuser", ctx)
        assert result.username == "testuser"
        fetcher.get_user_profile.assert_not_awaited()


class TestGetUserTimelineMetrics:
    async def test_returns_timeline(self):
        posts = [_make_post(like_count=100), _make_post(like_count=200)]
        fetcher = AsyncMock()
        fetcher.get_user_posts.return_value = posts
        ctx = _make_ctx(fetcher)

        result = await get_user_timeline_metrics("testuser", ctx=ctx)
        assert result.username == "testuser"
        assert result.summary.post_count == 2
        assert result.summary.total_engagements > 0

    async def test_empty_timeline(self):
        fetcher = AsyncMock()
        fetcher.get_user_posts.return_value = []
        ctx = _make_ctx(fetcher)

        result = await get_user_timeline_metrics("testuser", ctx=ctx)
        assert result.summary.post_count == 0
        assert result.summary.avg_engagement_rate == 0.0


class TestGetEngagementTimeseries:
    async def test_returns_timeseries(self):
        now = datetime.now(tz=timezone.utc)
        posts = [_make_post(like_count=100, created_at=now)]
        fetcher = AsyncMock()
        fetcher.get_user_posts.return_value = posts
        ctx = _make_ctx(fetcher)

        result = await get_engagement_timeseries("testuser", ctx, days_back=14)
        assert result.username == "testuser"
        assert result.granularity == "day"
        assert len(result.timeseries) == 2  # default metrics: like_count, engagement_rate


class TestAnalyzeBestPostingTimes:
    async def test_returns_heatmap(self):
        now = datetime.now(tz=timezone.utc)
        posts = [_make_post(created_at=now) for _ in range(5)]
        fetcher = AsyncMock()
        fetcher.get_user_posts.return_value = posts
        ctx = _make_ctx(fetcher)

        result = await analyze_best_posting_times("testuser", ctx)
        assert result.username == "testuser"
        assert result.sample_size > 0
        assert "very low" in result.confidence_note  # only 5 posts
