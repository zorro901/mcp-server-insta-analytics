"""Tests for the async SQLite rate limiter."""

from __future__ import annotations

import pytest

from mcp_insta_analytics.errors import BudgetExhaustedError, RateLimitError
from mcp_insta_analytics.rate_limiter import SqliteRateLimiter


@pytest.fixture
async def limiter(tmp_path):
    rl = SqliteRateLimiter(
        str(tmp_path / "rl.db"),
        max_per_minute=10,
        daily_budget=5,
    )
    await rl.initialize()
    yield rl
    await rl.close()


class TestSqliteRateLimiter:
    async def test_acquire_within_limits(self, limiter: SqliteRateLimiter):
        await limiter.acquire()
        await limiter.acquire()
        usage = await limiter.get_usage()
        assert usage.requests_this_minute == 2
        assert usage.requests_today == 2

    async def test_per_minute_limit_raises(self, tmp_path):
        rl = SqliteRateLimiter(str(tmp_path / "rl2.db"), max_per_minute=3, daily_budget=100)
        await rl.initialize()
        for _ in range(3):
            await rl.acquire()
        with pytest.raises(RateLimitError) as exc_info:
            await rl.acquire()
        assert exc_info.value.retry_after_seconds == 60
        await rl.close()

    async def test_daily_budget_raises(self, limiter: SqliteRateLimiter):
        for _ in range(5):
            await limiter.acquire()
        with pytest.raises(BudgetExhaustedError) as exc_info:
            await limiter.acquire()
        assert exc_info.value.daily_limit == 5

    async def test_usage_stats(self, limiter: SqliteRateLimiter):
        await limiter.acquire()
        usage = await limiter.get_usage()
        assert usage.requests_today == 1
        assert usage.remaining_today == 4
        assert usage.daily_budget == 5
        assert usage.per_minute_limit == 10
