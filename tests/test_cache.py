"""Tests for the async SQLite cache."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mcp_insta_analytics.cache import SqliteCache


@pytest.fixture
async def cache(tmp_path):
    c = SqliteCache(str(tmp_path / "cache.db"))
    await c.initialize()
    yield c
    await c.close()


class TestSqliteCache:
    async def test_set_get_roundtrip(self, cache: SqliteCache):
        await cache.set("key1", "value1", ttl=300)
        result = await cache.get("key1")
        assert result == "value1"

    async def test_get_missing_key_returns_none(self, cache: SqliteCache):
        result = await cache.get("nonexistent")
        assert result is None

    async def test_ttl_expiration(self, cache: SqliteCache):
        with patch("mcp_insta_analytics.cache.time") as mock_time:
            mock_time.time.return_value = 1000.0
            await cache.set("key1", "value1", ttl=60)

            mock_time.time.return_value = 1061.0
            result = await cache.get("key1")
            assert result is None

    async def test_delete(self, cache: SqliteCache):
        await cache.set("key1", "value1", ttl=300)
        await cache.delete("key1")
        result = await cache.get("key1")
        assert result is None

    async def test_upsert_overwrites(self, cache: SqliteCache):
        await cache.set("key1", "old", ttl=300)
        await cache.set("key1", "new", ttl=300)
        result = await cache.get("key1")
        assert result == "new"

    async def test_purge_expired(self, cache: SqliteCache):
        with patch("mcp_insta_analytics.cache.time") as mock_time:
            mock_time.time.return_value = 1000.0
            await cache.set("live", "alive", ttl=300)
            await cache.set("dead", "gone", ttl=10)

            mock_time.time.return_value = 1011.0
            await cache.purge_expired()

            assert await cache.get("live") == "alive"
            assert await cache.get("dead") is None
