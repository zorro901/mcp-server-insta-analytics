"""DynamoDB cache backend with TTL-based expiration."""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

from mcp_insta_analytics.cache import CacheBackend
from mcp_insta_analytics.errors import CacheError


class DynamoDBCache(CacheBackend):
    """DynamoDB-backed cache using single-table design.

    Items use ``PK=CACHE#{key}`` / ``SK=VALUE`` with a ``ttl`` attribute
    for automatic DynamoDB TTL deletion.  Reads use eventual consistency
    (0.5 RCU per read) with client-side TTL checks since DynamoDB TTL
    deletion can be delayed up to 48 hours.
    """

    def __init__(
        self,
        table_name: str,
        region: str = "ap-northeast-1",
        endpoint_url: str = "",
    ) -> None:
        self._table_name = table_name
        self._region = region
        self._endpoint_url = endpoint_url
        self._table: Any = None

    async def initialize(self) -> None:
        try:
            dynamodb = boto3.resource(
                "dynamodb",
                region_name=self._region,
                endpoint_url=self._endpoint_url or None,
            )
            self._table = dynamodb.Table(self._table_name)
            self._table.table_status  # noqa: B018
        except ClientError as exc:
            raise CacheError(f"Failed to initialize DynamoDB cache: {exc}") from exc

    async def get(self, key: str) -> str | None:
        if self._table is None:
            raise CacheError("Cache not initialized")
        try:
            response = self._table.get_item(
                Key={"PK": f"CACHE#{key}", "SK": "VALUE"},
                ConsistentRead=False,
            )
            item: dict[str, Any] | None = response.get("Item")
            if item is None:
                return None
            ttl_value = int(item.get("ttl", 0))
            if ttl_value <= int(time.time()):
                return None
            return str(item["value"])
        except ClientError as exc:
            raise CacheError(f"Cache get failed: {exc}") from exc

    async def set(self, key: str, value: str, ttl: int) -> None:
        if self._table is None:
            raise CacheError("Cache not initialized")
        try:
            expires_at = int(time.time()) + ttl
            self._table.put_item(
                Item={
                    "PK": f"CACHE#{key}",
                    "SK": "VALUE",
                    "value": value,
                    "ttl": expires_at,
                },
            )
        except ClientError as exc:
            raise CacheError(f"Cache set failed: {exc}") from exc

    async def delete(self, key: str) -> None:
        if self._table is None:
            raise CacheError("Cache not initialized")
        try:
            self._table.delete_item(
                Key={"PK": f"CACHE#{key}", "SK": "VALUE"},
            )
        except ClientError as exc:
            raise CacheError(f"Cache delete failed: {exc}") from exc

    async def purge_expired(self) -> None:
        """No-op: DynamoDB TTL handles automatic expiration."""

    async def close(self) -> None:
        """No-op: boto3 resources do not require explicit cleanup."""
        self._table = None
