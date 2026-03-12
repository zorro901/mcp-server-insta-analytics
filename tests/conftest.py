"""Shared pytest fixtures for the Instagram Analytics MCP server test suite."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_insta_analytics.cache import SqliteCache
from mcp_insta_analytics.config import Settings
from mcp_insta_analytics.fetcher.base import AbstractFetcher
from mcp_insta_analytics.models import Comment, Post, UserProfile
from mcp_insta_analytics.rate_limiter import SqliteRateLimiter

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ------------------------------------------------------------------
# Raw JSON data fixtures
# ------------------------------------------------------------------


@pytest.fixture
def sample_post_data():
    return json.loads((FIXTURES_DIR / "sample_post.json").read_text())


@pytest.fixture
def sample_user_data():
    return json.loads((FIXTURES_DIR / "sample_user.json").read_text())


@pytest.fixture
def sample_comments_data():
    return json.loads((FIXTURES_DIR / "sample_comments.json").read_text())


# ------------------------------------------------------------------
# Pydantic model fixtures
# ------------------------------------------------------------------


@pytest.fixture
def sample_post(sample_post_data):
    return Post(**sample_post_data)


@pytest.fixture
def sample_user(sample_user_data):
    return UserProfile(**sample_user_data)


@pytest.fixture
def sample_comments(sample_comments_data):
    return [Comment(**c) for c in sample_comments_data]


# ------------------------------------------------------------------
# Configuration fixture
# ------------------------------------------------------------------


@pytest.fixture
def test_config():
    return Settings(
        fetcher_backend="instaloader",
        cache_db_path="/tmp/test-insta-analytics-cache.db",
        cache_ttl_posts=300,
        cache_ttl_profiles=600,
        cache_ttl_search=120,
        max_requests_per_minute=100,
        daily_request_budget=10000,
    )


# ------------------------------------------------------------------
# Mock fetcher
# ------------------------------------------------------------------


@pytest.fixture
def mock_fetcher(sample_post, sample_user, sample_comments):
    fetcher = AsyncMock(spec=AbstractFetcher)
    fetcher.get_post_detail.return_value = sample_post
    fetcher.get_user_profile.return_value = sample_user
    fetcher.get_user_posts.return_value = [sample_post] * 5
    fetcher.get_hashtag_posts.return_value = [sample_post] * 10
    fetcher.get_post_comments.return_value = sample_comments
    return fetcher


# ------------------------------------------------------------------
# Async infrastructure fixtures
# ------------------------------------------------------------------


@pytest.fixture
async def test_cache(tmp_path):
    cache = SqliteCache(str(tmp_path / "test_cache.db"))
    await cache.initialize()
    yield cache
    await cache.close()


@pytest.fixture
async def test_rate_limiter(tmp_path):
    rl = SqliteRateLimiter(
        str(tmp_path / "test_rl.db"),
        max_per_minute=100,
        daily_budget=10000,
    )
    await rl.initialize()
    yield rl
    await rl.close()


# ------------------------------------------------------------------
# Mock MCP context
# ------------------------------------------------------------------


@pytest.fixture
def mock_context(mock_fetcher, test_cache, test_rate_limiter, test_config):
    ctx = MagicMock()
    ctx.lifespan_context = {
        "fetcher": mock_fetcher,
        "cache": test_cache,
        "rate_limiter": test_rate_limiter,
        "config": test_config,
    }
    return ctx
