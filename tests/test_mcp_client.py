"""Integration tests using the FastMCP Client to verify MCP tool calls end-to-end.

These tests create a fresh FastMCP server per test with a mock fetcher injected
via a custom lifespan, then use the FastMCP Client (in-process transport) to call
each tool through the MCP protocol — exactly as Claude Desktop would.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from fastmcp import Client, FastMCP

from mcp_insta_analytics.cache import SqliteCache
from mcp_insta_analytics.config import Settings
from mcp_insta_analytics.models import Comment, Post, UserProfile
from mcp_insta_analytics.rate_limiter import SqliteRateLimiter


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(tz=timezone.utc)


def _make_post(
    id: str = "1234567890",
    shortcode: str = "ABC123",
    caption: str = "Beautiful sunset! #travel #photography",
    like_count: int = 350,
    comment_count: int = 42,
    view_count: int = 0,
    author_id: str = "987654321",
    author_username: str = "testuser",
    created_at: datetime | None = None,
    hashtags: list[str] | None = None,
    media_type: str = "image",
) -> Post:
    return Post(
        id=id,
        shortcode=shortcode,
        caption=caption,
        like_count=like_count,
        comment_count=comment_count,
        view_count=view_count,
        author_id=author_id,
        author_username=author_username,
        created_at=created_at or _NOW - timedelta(hours=1),
        hashtags=hashtags or ["travel", "photography"],
        media_type=media_type,
    )


def _make_profile(
    id: str = "987654321",
    username: str = "testuser",
    followers_count: int = 5000,
    following_count: int = 500,
    media_count: int = 365,
) -> UserProfile:
    return UserProfile(
        id=id,
        username=username,
        full_name="Test User",
        biography="Travel photographer",
        followers_count=followers_count,
        following_count=following_count,
        media_count=media_count,
        is_verified=False,
        is_private=False,
        created_at=datetime(2020, 1, 15, 0, 0, tzinfo=timezone.utc),
    )


def _make_comment(id: str, text: str, author: str) -> Comment:
    return Comment(
        id=id,
        text=text,
        author_username=author,
        created_at=_NOW - timedelta(minutes=30),
        like_count=5,
    )


def _default_mock_fetcher() -> AsyncMock:
    """Pre-configured mock fetcher with sensible return values."""
    fetcher = AsyncMock()

    sample_post = _make_post()
    sample_posts = [
        _make_post(id=str(i), shortcode=f"SC{i}", like_count=100 + i * 10,
                   created_at=_NOW - timedelta(hours=i))
        for i in range(5)
    ]
    sample_profile = _make_profile()
    sample_comments = [
        _make_comment("c1", "Love this! Amazing work!", "fan1"),
        _make_comment("c2", "This is terrible and disappointing.", "critic1"),
        _make_comment("c3", "Interesting perspective on the topic.", "neutral1"),
    ]

    fetcher.get_post_detail.return_value = sample_post
    fetcher.get_user_profile.return_value = sample_profile
    fetcher.get_user_posts.return_value = sample_posts
    fetcher.get_hashtag_posts.return_value = sample_posts
    fetcher.get_post_comments.return_value = sample_comments
    fetcher.close.return_value = None

    return fetcher


# ---------------------------------------------------------------------------
# Helper: build a fresh server + client per test
# ---------------------------------------------------------------------------


def _build_server(mock_fetcher: AsyncMock, tmp_path_str: str) -> FastMCP:
    """Create a new FastMCP server with all tools registered and a test lifespan."""
    from mcp_insta_analytics.tools.post_metrics import compare_post_performance, get_post_metrics
    from mcp_insta_analytics.tools.search import search_posts_by_hashtag, track_hashtag_trend
    from mcp_insta_analytics.tools.user_analytics import (
        analyze_best_posting_times,
        get_engagement_timeseries,
        get_user_profile_analytics,
        get_user_timeline_metrics,
    )
    from mcp_insta_analytics.tools.comments import analyze_comment_sentiment, get_post_comments

    @asynccontextmanager
    async def test_lifespan(_server: FastMCP) -> AsyncIterator[dict[str, object]]:
        config = Settings(
            cache_db_path=f"{tmp_path_str}/test_cache.db",
            max_requests_per_minute=100,
            daily_request_budget=10000,
        )
        cache = SqliteCache(f"{tmp_path_str}/test_cache.db")
        await cache.initialize()
        rate_limiter = SqliteRateLimiter(
            f"{tmp_path_str}/test_rl.db",
            max_per_minute=100,
            daily_budget=10000,
        )
        await rate_limiter.initialize()
        try:
            yield {
                "fetcher": mock_fetcher,
                "cache": cache,
                "rate_limiter": rate_limiter,
                "config": config,
                "auth_error": None,
            }
        finally:
            await cache.close()
            await rate_limiter.close()

    server = FastMCP("Instagram Analytics Test", lifespan=test_lifespan)

    # Register all tools (same as server.py)
    server.tool(name="get_post_metrics")(get_post_metrics)
    server.tool(name="compare_post_performance")(compare_post_performance)
    server.tool(name="search_posts_by_hashtag")(search_posts_by_hashtag)
    server.tool(name="track_hashtag_trend")(track_hashtag_trend)
    server.tool(name="get_user_profile_analytics")(get_user_profile_analytics)
    server.tool(name="get_user_timeline_metrics")(get_user_timeline_metrics)
    server.tool(name="get_engagement_timeseries")(get_engagement_timeseries)
    server.tool(name="analyze_best_posting_times")(analyze_best_posting_times)
    server.tool(name="get_post_comments")(get_post_comments)
    server.tool(name="analyze_comment_sentiment")(analyze_comment_sentiment)

    return server


# ---------------------------------------------------------------------------
# Tests: Tool discovery
# ---------------------------------------------------------------------------


class TestToolDiscovery:
    """Verify that all 10 tools are registered and discoverable."""

    async def test_all_tools_listed(self, tmp_path) -> None:
        fetcher = _default_mock_fetcher()
        server = _build_server(fetcher, str(tmp_path))
        async with Client(server) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}

        expected = {
            "get_post_metrics",
            "compare_post_performance",
            "search_posts_by_hashtag",
            "track_hashtag_trend",
            "get_user_profile_analytics",
            "get_user_timeline_metrics",
            "get_engagement_timeseries",
            "analyze_best_posting_times",
            "get_post_comments",
            "analyze_comment_sentiment",
        }

        assert expected.issubset(tool_names), f"Missing tools: {expected - tool_names}"


# ---------------------------------------------------------------------------
# Tests: Post metrics tools
# ---------------------------------------------------------------------------


class TestGetPostMetricsClient:
    """Test get_post_metrics via MCP Client."""

    async def test_returns_metrics(self, tmp_path) -> None:
        fetcher = _default_mock_fetcher()
        server = _build_server(fetcher, str(tmp_path))
        async with Client(server) as client:
            result = await client.call_tool("get_post_metrics", {"shortcode": "ABC123"})

        assert not result.is_error
        data = json.loads(result.content[0].text)
        assert data["id"] == "1234567890"
        assert data["engagement_rate"] > 0
        assert data["total_engagements"] > 0


class TestComparePostPerformanceClient:
    """Test compare_post_performance via MCP Client."""

    async def test_returns_ranked_comparison(self, tmp_path) -> None:
        fetcher = _default_mock_fetcher()
        post_a = _make_post(id="a", shortcode="a", like_count=200, comment_count=50)
        post_b = _make_post(id="b", shortcode="b", like_count=50, comment_count=10)
        fetcher.get_post_detail.side_effect = [post_a, post_b]

        server = _build_server(fetcher, str(tmp_path))
        async with Client(server) as client:
            result = await client.call_tool(
                "compare_post_performance",
                {"shortcodes": ["a", "b"], "rank_by": "engagement_rate"},
            )

        assert not result.is_error
        data = json.loads(result.content[0].text)
        assert len(data["ranked_posts"]) == 2
        assert "statistics" in data

    async def test_validation_error_single_id(self, tmp_path) -> None:
        fetcher = _default_mock_fetcher()
        server = _build_server(fetcher, str(tmp_path))
        async with Client(server) as client:
            result = await client.call_tool(
                "compare_post_performance",
                {"shortcodes": ["only_one"], "rank_by": "engagement_rate"},
            )

        assert not result.is_error
        data = json.loads(result.content[0].text)
        assert data["error"] == "InvalidInput"


# ---------------------------------------------------------------------------
# Tests: Search tools
# ---------------------------------------------------------------------------


class TestSearchPostsByHashtagClient:
    """Test search_posts_by_hashtag via MCP Client."""

    async def test_returns_search_results(self, tmp_path) -> None:
        fetcher = _default_mock_fetcher()
        server = _build_server(fetcher, str(tmp_path))
        async with Client(server) as client:
            result = await client.call_tool(
                "search_posts_by_hashtag", {"hashtag": "travel"}
            )

        assert not result.is_error
        data = json.loads(result.content[0].text)
        assert data["hashtag"] == "#travel"
        assert data["total_results"] > 0
        assert len(data["posts"]) > 0


# ---------------------------------------------------------------------------
# Tests: User analytics tools
# ---------------------------------------------------------------------------


class TestGetUserProfileAnalyticsClient:
    """Test get_user_profile_analytics via MCP Client."""

    async def test_returns_profile_analytics(self, tmp_path) -> None:
        fetcher = _default_mock_fetcher()
        server = _build_server(fetcher, str(tmp_path))
        async with Client(server) as client:
            result = await client.call_tool(
                "get_user_profile_analytics",
                {"username": "testuser"},
            )

        assert not result.is_error
        data = json.loads(result.content[0].text)
        assert data["username"] == "testuser"
        assert data["followers_count"] == 5000
        assert data["follower_following_ratio"] > 0


class TestGetUserTimelineMetricsClient:
    """Test get_user_timeline_metrics via MCP Client."""

    async def test_returns_timeline_with_summary(self, tmp_path) -> None:
        fetcher = _default_mock_fetcher()
        server = _build_server(fetcher, str(tmp_path))
        async with Client(server) as client:
            result = await client.call_tool(
                "get_user_timeline_metrics",
                {"username": "testuser", "max_results": 20},
            )

        assert not result.is_error
        data = json.loads(result.content[0].text)
        assert data["username"] == "testuser"
        assert len(data["posts"]) > 0
        assert data["summary"]["post_count"] > 0
        assert data["summary"]["avg_engagement_rate"] > 0


# ---------------------------------------------------------------------------
# Tests: Comment tools
# ---------------------------------------------------------------------------


class TestGetPostCommentsClient:
    """Test get_post_comments via MCP Client."""

    async def test_returns_comments(self, tmp_path) -> None:
        fetcher = _default_mock_fetcher()
        server = _build_server(fetcher, str(tmp_path))
        async with Client(server) as client:
            result = await client.call_tool(
                "get_post_comments",
                {"shortcode": "ABC123"},
            )

        assert not result.is_error
        data = json.loads(result.content[0].text)
        assert data["post_id"] == "ABC123"
        assert data["total_comments"] == 3
        assert len(data["comments"]) == 3


class TestAnalyzeCommentSentimentClient:
    """Test analyze_comment_sentiment via MCP Client."""

    async def test_returns_sentiment_analysis(self, tmp_path) -> None:
        fetcher = _default_mock_fetcher()
        server = _build_server(fetcher, str(tmp_path))
        async with Client(server) as client:
            result = await client.call_tool(
                "analyze_comment_sentiment",
                {"shortcode": "ABC123"},
            )

        assert not result.is_error
        data = json.loads(result.content[0].text)
        assert data["post_id"] == "ABC123"
        assert data["sentiment_summary"] is not None
        assert data["sentiment_summary"]["total_analyzed"] == 3


# ---------------------------------------------------------------------------
# Tests: Engagement timeseries & posting times
# ---------------------------------------------------------------------------


class TestGetEngagementTimeseriesClient:
    """Test get_engagement_timeseries via MCP Client."""

    async def test_returns_timeseries(self, tmp_path) -> None:
        fetcher = _default_mock_fetcher()
        server = _build_server(fetcher, str(tmp_path))
        async with Client(server) as client:
            result = await client.call_tool(
                "get_engagement_timeseries",
                {"username": "testuser"},
            )

        assert not result.is_error
        data = json.loads(result.content[0].text)
        assert data["username"] == "testuser"
        assert data["granularity"] == "day"
        assert len(data["timeseries"]) == 2  # default: like_count + engagement_rate


class TestAnalyzeBestPostingTimesClient:
    """Test analyze_best_posting_times via MCP Client."""

    async def test_returns_heatmap(self, tmp_path) -> None:
        fetcher = _default_mock_fetcher()
        server = _build_server(fetcher, str(tmp_path))
        async with Client(server) as client:
            result = await client.call_tool(
                "analyze_best_posting_times",
                {"username": "testuser"},
            )

        assert not result.is_error
        data = json.loads(result.content[0].text)
        assert data["username"] == "testuser"
        assert data["timezone"] == "Asia/Tokyo"
        assert data["metric"] == "engagement_rate"
        assert "heatmap" in data
        assert "confidence_note" in data
