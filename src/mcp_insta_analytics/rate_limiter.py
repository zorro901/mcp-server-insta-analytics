"""Token-bucket rate limiter with per-minute and daily limits."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path

import aiosqlite

from mcp_insta_analytics.errors import BudgetExhaustedError, RateLimitError
from mcp_insta_analytics.models import UsageStats


class RateLimiterBackend(ABC):
    """Abstract rate limiter backend interface."""

    @abstractmethod
    async def initialize(self) -> None: ...

    @abstractmethod
    async def acquire(self) -> None: ...

    @abstractmethod
    async def get_usage(self) -> UsageStats: ...

    @abstractmethod
    async def close(self) -> None: ...


_SECONDS_PER_MINUTE = 60
_SECONDS_PER_DAY = 86400


class SqliteRateLimiter(RateLimiterBackend):
    """Persistent rate limiter using aiosqlite to track request timestamps."""

    def __init__(
        self,
        db_path: str,
        max_per_minute: int = 15,
        daily_budget: int = 500,
    ) -> None:
        self._db_path = Path(db_path).expanduser()
        self._max_per_minute = max_per_minute
        self._daily_budget = daily_budget
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._db_path))
        await self._db.execute(
            "CREATE TABLE IF NOT EXISTS request_log "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL)"
        )
        await self._db.commit()
        cutoff = time.time() - _SECONDS_PER_DAY
        await self._db.execute("DELETE FROM request_log WHERE timestamp < ?", (cutoff,))
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def _count_since(self, cutoff: float) -> int:
        assert self._db is not None, "RateLimiter not initialized"
        async with self._db.execute(
            "SELECT COUNT(*) FROM request_log WHERE timestamp >= ?", (cutoff,)
        ) as cursor:
            row = await cursor.fetchone()  # type: ignore[misc]
        if row is None:
            return 0
        return int(row[0])

    async def acquire(self) -> None:
        assert self._db is not None, "RateLimiter not initialized"
        now = time.time()
        requests_today = await self._count_since(now - _SECONDS_PER_DAY)
        if requests_today >= self._daily_budget:
            raise BudgetExhaustedError(daily_limit=self._daily_budget)
        requests_this_minute = await self._count_since(now - _SECONDS_PER_MINUTE)
        if requests_this_minute >= self._max_per_minute:
            remaining_daily = self._daily_budget - requests_today
            raise RateLimitError(
                retry_after_seconds=_SECONDS_PER_MINUTE,
                remaining_daily=remaining_daily,
            )
        await self._db.execute("INSERT INTO request_log (timestamp) VALUES (?)", (now,))
        await self._db.commit()

    async def get_usage(self) -> UsageStats:
        now = time.time()
        requests_today = await self._count_since(now - _SECONDS_PER_DAY)
        requests_this_minute = await self._count_since(now - _SECONDS_PER_MINUTE)
        return UsageStats(
            requests_today=requests_today,
            daily_budget=self._daily_budget,
            remaining_today=max(0, self._daily_budget - requests_today),
            requests_this_minute=requests_this_minute,
            per_minute_limit=self._max_per_minute,
        )
