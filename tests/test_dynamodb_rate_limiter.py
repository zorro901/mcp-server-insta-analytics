"""Tests for the DynamoDB rate limiter backend using moto."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from mcp_insta_analytics.dynamodb_rate_limiter import DynamoDBRateLimiter
from mcp_insta_analytics.errors import BudgetExhaustedError, RateLimitError

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
async def limiter(_dynamodb_table):
    """Provide an initialized DynamoDBRateLimiter with low limits."""
    with mock_aws():
        rl = DynamoDBRateLimiter(
            table_name=TABLE_NAME,
            region=REGION,
            max_per_minute=5,
            daily_budget=20,
        )
        await rl.initialize()
        yield rl
        await rl.close()


class TestDynamoDBRateLimiter:
    """Tests for DynamoDBRateLimiter acquire, limits, and usage stats."""

    async def test_acquire_succeeds_within_limits(self, limiter: DynamoDBRateLimiter) -> None:
        await limiter.acquire()

    async def test_acquire_multiple_within_limits(self, limiter: DynamoDBRateLimiter) -> None:
        for _ in range(5):
            await limiter.acquire()

    async def test_acquire_raises_rate_limit_error_when_per_minute_exceeded(
        self, limiter: DynamoDBRateLimiter
    ) -> None:
        for _ in range(5):
            await limiter.acquire()

        with pytest.raises(RateLimitError):
            await limiter.acquire()

    async def test_acquire_raises_budget_exhausted_when_daily_limit_exceeded(
        self, _dynamodb_table
    ) -> None:
        with mock_aws():
            rl = DynamoDBRateLimiter(
                table_name=TABLE_NAME,
                region=REGION,
                max_per_minute=100,
                daily_budget=3,
            )
            await rl.initialize()

            for _ in range(3):
                await rl.acquire()

            with pytest.raises(BudgetExhaustedError) as exc_info:
                await rl.acquire()

            assert exc_info.value.daily_limit == 3
            await rl.close()

    async def test_get_usage_returns_correct_stats(
        self, limiter: DynamoDBRateLimiter
    ) -> None:
        usage = await limiter.get_usage()
        assert usage.requests_today == 0
        assert usage.daily_budget == 20
        assert usage.remaining_today == 20
        assert usage.requests_this_minute == 0
        assert usage.per_minute_limit == 5

    async def test_get_usage_after_requests(self, limiter: DynamoDBRateLimiter) -> None:
        await limiter.acquire()
        await limiter.acquire()
        await limiter.acquire()

        usage = await limiter.get_usage()
        assert usage.requests_today == 3
        assert usage.remaining_today == 17
        assert usage.requests_this_minute == 3
