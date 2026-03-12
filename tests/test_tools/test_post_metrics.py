"""Tests for post metrics tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock


from mcp_insta_analytics.models import Post
from mcp_insta_analytics.tools.post_metrics import compare_post_performance, get_post_metrics


def _make_ctx(
    fetcher: AsyncMock,
    cache: AsyncMock | None = None,
    rate_limiter: AsyncMock | None = None,
    config: MagicMock | None = None,
) -> MagicMock:
    ctx = MagicMock()
    if cache is None:
        cache = AsyncMock()
        cache.get.return_value = None
    if rate_limiter is None:
        rate_limiter = AsyncMock()
    if config is None:
        config = MagicMock()
        config.cache_ttl_posts = 300
    ctx.lifespan_context = {
        "fetcher": fetcher,
        "cache": cache,
        "rate_limiter": rate_limiter,
        "config": config,
    }
    return ctx


def _make_post(post_id: str = "1", like_count: int = 100, comment_count: int = 10) -> Post:
    return Post(
        id=post_id,
        shortcode=f"sc_{post_id}",
        like_count=like_count,
        comment_count=comment_count,
    )


class TestGetPostMetrics:
    async def test_returns_post_with_metrics(self):
        post = _make_post()
        fetcher = AsyncMock()
        fetcher.get_post_detail.return_value = post
        cache = AsyncMock()
        cache.get.return_value = None
        ctx = _make_ctx(fetcher, cache=cache)

        result = await get_post_metrics("sc_1", ctx)
        assert result.id == "1"
        assert result.engagement_rate > 0
        assert result.total_engagements == 110

    async def test_cache_hit(self):
        post = _make_post()
        fetcher = AsyncMock()
        cache = AsyncMock()
        cache.get.return_value = json.dumps(post.model_dump(mode="json"))
        ctx = _make_ctx(fetcher, cache=cache)

        result = await get_post_metrics("sc_1", ctx)
        assert result.id == "1"
        fetcher.get_post_detail.assert_not_awaited()


class TestComparePostPerformance:
    async def test_ranks_posts(self):
        posts = [_make_post("1", like_count=50), _make_post("2", like_count=500)]
        fetcher = AsyncMock()
        fetcher.get_post_detail.side_effect = posts
        cache = AsyncMock()
        cache.get.return_value = None
        ctx = _make_ctx(fetcher, cache=cache)

        result = await compare_post_performance(["sc_1", "sc_2"], "engagement_rate", ctx)
        assert hasattr(result, "ranked_posts")
        assert len(result.ranked_posts) == 2

    async def test_too_few_posts_returns_error(self):
        fetcher = AsyncMock()
        ctx = _make_ctx(fetcher)

        result = await compare_post_performance(["sc_1"], "engagement_rate", ctx)
        assert hasattr(result, "error")
        assert result.message == "shortcodes must contain between 2 and 20 items."

    async def test_statistics_present(self):
        posts = [_make_post("1", like_count=100), _make_post("2", like_count=200)]
        fetcher = AsyncMock()
        fetcher.get_post_detail.side_effect = posts
        cache = AsyncMock()
        cache.get.return_value = None
        ctx = _make_ctx(fetcher, cache=cache)

        result = await compare_post_performance(["sc_1", "sc_2"], "engagement_rate", ctx)
        assert "engagement_rate" in result.statistics
        assert result.statistics["engagement_rate"].max >= result.statistics["engagement_rate"].min
