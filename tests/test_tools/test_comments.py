"""Tests for comment and sentiment tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from mcp_insta_analytics.models import Comment
from mcp_insta_analytics.tools.comments import analyze_comment_sentiment, get_post_comments


def _make_ctx(fetcher: AsyncMock) -> MagicMock:
    ctx = MagicMock()
    cache = AsyncMock()
    cache.get.return_value = None  # No cached comments
    config = MagicMock()
    config.cache_ttl_posts = 900
    ctx.lifespan_context = {
        "fetcher": fetcher,
        "cache": cache,
        "rate_limiter": AsyncMock(),
        "config": config,
    }
    return ctx


def _make_comments() -> list[Comment]:
    return [
        Comment(id="1", text="Amazing photo!", like_count=10),
        Comment(id="2", text="This is terrible", like_count=1),
        Comment(id="3", text="Nice view", like_count=5),
    ]


class TestGetPostComments:
    async def test_returns_thread(self):
        comments = _make_comments()
        fetcher = AsyncMock()
        fetcher.get_post_comments.return_value = comments
        ctx = _make_ctx(fetcher)

        result = await get_post_comments("abc123", ctx)
        assert result.post_id == "abc123"
        assert result.total_comments == 3
        assert len(result.comments) == 3


class TestAnalyzeCommentSentiment:
    async def test_returns_sentiment(self):
        comments = _make_comments()
        fetcher = AsyncMock()
        fetcher.get_post_comments.return_value = comments
        ctx = _make_ctx(fetcher)

        result = await analyze_comment_sentiment("abc123", ctx)
        assert result.post_id == "abc123"
        assert result.sentiment_summary is not None
        assert result.sentiment_summary.total_analyzed == 3

    async def test_empty_comments(self):
        fetcher = AsyncMock()
        fetcher.get_post_comments.return_value = []
        ctx = _make_ctx(fetcher)

        result = await analyze_comment_sentiment("abc123", ctx)
        assert result.sentiment_summary is None
        assert result.individual_sentiments.most_positive == []
        assert result.individual_sentiments.most_negative == []
