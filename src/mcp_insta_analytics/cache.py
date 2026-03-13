"""Async cache with TTL-based expiration."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite

from mcp_insta_analytics.errors import CacheError


class CacheBackend(ABC):
    """Abstract cache backend interface."""

    @abstractmethod
    async def initialize(self) -> None: ...

    @abstractmethod
    async def get(self, key: str) -> str | None: ...

    @abstractmethod
    async def set(self, key: str, value: str, ttl: int) -> None: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def purge_expired(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS cache (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    expires_at INTEGER NOT NULL
)
"""

_PURGE_EXPIRED = "DELETE FROM cache WHERE expires_at <= ?"
_GET = "SELECT value FROM cache WHERE key = ? AND expires_at > ?"
_UPSERT = """
INSERT INTO cache (key, value, expires_at) VALUES (?, ?, ?)
ON CONFLICT(key) DO UPDATE SET value = excluded.value, expires_at = excluded.expires_at
"""
_DELETE = "DELETE FROM cache WHERE key = ?"


class SqliteCache(CacheBackend):
    """Async SQLite cache with automatic expiration."""

    def __init__(self, db_path: str) -> None:
        import aiosqlite as _aiosqlite  # noqa: F811

        self._aiosqlite = _aiosqlite
        self._db_path = Path(db_path).expanduser()
        self._db: aiosqlite.Connection | None = None

    @property
    def db_path(self) -> Path:
        """Return the resolved database file path."""
        return self._db_path

    async def initialize(self) -> None:
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = await self._aiosqlite.connect(str(self._db_path))
            await self._db.execute(_CREATE_TABLE)
            await self._db.commit()
            await self.purge_expired()
        except self._aiosqlite.Error as exc:
            raise CacheError(f"Failed to initialize cache: {exc}") from exc

    async def get(self, key: str) -> str | None:
        if self._db is None:
            raise CacheError("Cache not initialized")
        try:
            now = int(time.time())
            cursor = await self._db.execute(_GET, (key, now))
            row = await cursor.fetchone()
            return row[0] if row else None
        except self._aiosqlite.Error as exc:
            raise CacheError(f"Cache get failed: {exc}") from exc

    async def set(self, key: str, value: str, ttl: int) -> None:
        if self._db is None:
            raise CacheError("Cache not initialized")
        try:
            expires_at = int(time.time()) + ttl
            await self._db.execute(_UPSERT, (key, value, expires_at))
            await self._db.commit()
        except self._aiosqlite.Error as exc:
            raise CacheError(f"Cache set failed: {exc}") from exc

    async def delete(self, key: str) -> None:
        if self._db is None:
            raise CacheError("Cache not initialized")
        try:
            await self._db.execute(_DELETE, (key,))
            await self._db.commit()
        except self._aiosqlite.Error as exc:
            raise CacheError(f"Cache delete failed: {exc}") from exc

    async def purge_expired(self) -> None:
        if self._db is None:
            raise CacheError("Cache not initialized")
        try:
            now = int(time.time())
            await self._db.execute(_PURGE_EXPIRED, (now,))
            await self._db.commit()
        except self._aiosqlite.Error as exc:
            raise CacheError(f"Cache purge failed: {exc}") from exc

    async def close(self) -> None:
        if self._db is not None:
            try:
                await self._db.close()
            except self._aiosqlite.Error as exc:
                raise CacheError(f"Cache close failed: {exc}") from exc
            finally:
                self._db = None
