"""Tests for search and hashtag tools."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from mcp_insta_analytics.models import Post
from mcp_insta_analytics.tools.search import search_posts_by_hashtag, track_hashtag_trend


def _make_ctx(fetcher: AsyncMock) -> MagicMock:
    ctx = MagicMock()
    ctx.lifespan_context = {
        "fetcher": fetcher,
        "cache": AsyncMock(),
        "rate_limiter": AsyncMock(),
        "config": MagicMock(cache_ttl_search=120),
    }
    return ctx


def _make_post(
    like_count: int = 100,
    comment_count: int = 10,
    hashtags: list[str] | None = None,
    created_at: datetime | None = None,
) -> Post:
    return Post(
        id="1",
        shortcode="abc",
        like_count=like_count,
        comment_count=comment_count,
        hashtags=hashtags or [],
        created_at=created_at,
    )


class TestSearchPostsByHashtag:
    async def test_returns_results_with_metrics(self):
        posts = [_make_post(like_count=50), _make_post(like_count=200)]
        fetcher = AsyncMock()
        fetcher.get_hashtag_posts.return_value = posts
        ctx = _make_ctx(fetcher)

        result = await search_posts_by_hashtag("python", ctx=ctx)
        assert result.hashtag == "#python"
        assert result.total_results == 2
        assert len(result.posts) == 2

    async def test_strips_hash_prefix(self):
        fetcher = AsyncMock()
        fetcher.get_hashtag_posts.return_value = []
        ctx = _make_ctx(fetcher)

        await search_posts_by_hashtag("#python", ctx=ctx)
        fetcher.get_hashtag_posts.assert_awaited_once_with("python", count=25)

    async def test_sort_by_engagement_rate(self):
        posts = [_make_post(like_count=10), _make_post(like_count=1000)]
        fetcher = AsyncMock()
        fetcher.get_hashtag_posts.return_value = posts
        ctx = _make_ctx(fetcher)

        result = await search_posts_by_hashtag("test", sort_order="engagement_rate", ctx=ctx)
        rates = [p.engagement_rate for p in result.posts]
        assert rates == sorted(rates, reverse=True)


class TestTrackHashtagTrend:
    async def test_returns_performance_result(self):
        now = datetime.now(tz=timezone.utc)
        posts = [
            _make_post(
                like_count=100,
                hashtags=["sunset", "tokyo"],
                created_at=now,
            )
        ]
        fetcher = AsyncMock()
        fetcher.get_hashtag_posts.return_value = posts
        ctx = _make_ctx(fetcher)

        result = await track_hashtag_trend("sunset", ctx, days_back=7)
        assert result.hashtag == "#sunset"
        assert result.total_posts == 1
        assert result.average_engagement > 0

    async def test_co_occurring_hashtags(self):
        now = datetime.now(tz=timezone.utc)
        posts = [
            _make_post(hashtags=["sunset", "tokyo", "japan"], created_at=now),
            _make_post(hashtags=["sunset", "tokyo"], created_at=now),
        ]
        fetcher = AsyncMock()
        fetcher.get_hashtag_posts.return_value = posts
        ctx = _make_ctx(fetcher)

        result = await track_hashtag_trend("sunset", ctx, days_back=7)
        co_tags = dict(result.co_occurring_hashtags)
        assert "tokyo" in co_tags
        assert co_tags["tokyo"] == 2

    async def test_empty_posts_returns_zero(self):
        fetcher = AsyncMock()
        fetcher.get_hashtag_posts.return_value = []
        ctx = _make_ctx(fetcher)

        result = await track_hashtag_trend("empty", ctx)
        assert result.total_posts == 0
        assert result.average_engagement == 0.0
