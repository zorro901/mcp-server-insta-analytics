"""Tests for the DynamoDB cache backend using moto."""

from __future__ import annotations

import time
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from mcp_insta_analytics.dynamodb_cache import DynamoDBCache

TABLE_NAME = "test-mcp-insta-analytics"
REGION = "us-east-1"


@pytest.fixture()
def _dynamodb_table():
    """Create a mocked DynamoDB table for testing."""
    with mock_aws():
        client = boto3.client("dynamodb", region_name=REGION)
        client.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield


@pytest.fixture()
async def cache(_dynamodb_table):
    """Provide an initialized DynamoDBCache backed by moto."""
    with mock_aws():
        c = DynamoDBCache(table_name=TABLE_NAME, region=REGION)
        await c.initialize()
        yield c
        await c.close()


class TestDynamoDBCache:
    """Tests for DynamoDBCache set / get / delete operations."""

    async def test_set_and_get_roundtrip(self, cache: DynamoDBCache) -> None:
        await cache.set("key1", "value1", ttl=300)
        result = await cache.get("key1")
        assert result == "value1"

    async def test_get_returns_none_for_missing_key(self, cache: DynamoDBCache) -> None:
        result = await cache.get("nonexistent")
        assert result is None

    async def test_get_returns_none_for_expired_entry(self, cache: DynamoDBCache) -> None:
        await cache.set("expiring", "temp", ttl=10)

        future_time = time.time() + 11
        with patch("mcp_insta_analytics.dynamodb_cache.time") as mock_time:
            mock_time.time.return_value = future_time
            result = await cache.get("expiring")

        assert result is None

    async def test_delete_removes_entry(self, cache: DynamoDBCache) -> None:
        await cache.set("to_delete", "gone_soon", ttl=300)
        await cache.delete("to_delete")
        result = await cache.get("to_delete")
        assert result is None

    async def test_delete_nonexistent_key_does_not_raise(self, cache: DynamoDBCache) -> None:
        await cache.delete("never_existed")

    async def test_purge_expired_is_noop(self, cache: DynamoDBCache) -> None:
        await cache.purge_expired()

    async def test_upsert_updates_existing_key(self, cache: DynamoDBCache) -> None:
        await cache.set("updatable", "original", ttl=300)
        result_before = await cache.get("updatable")
        assert result_before == "original"

        await cache.set("updatable", "updated", ttl=300)
        result_after = await cache.get("updatable")
        assert result_after == "updated"

    async def test_upsert_updates_ttl(self, cache: DynamoDBCache) -> None:
        await cache.set("extend_me", "value", ttl=5)
        await cache.set("extend_me", "value", ttl=600)

        future_time = time.time() + 10
        with patch("mcp_insta_analytics.dynamodb_cache.time") as mock_time:
            mock_time.time.return_value = future_time
            result = await cache.get("extend_me")

        assert result == "value"
