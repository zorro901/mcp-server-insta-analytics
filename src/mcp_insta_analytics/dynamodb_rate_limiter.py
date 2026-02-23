"""DynamoDB rate limiter using atomic counter increments."""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

from mcp_insta_analytics.errors import BudgetExhaustedError, RateLimitError
from mcp_insta_analytics.models import UsageStats
from mcp_insta_analytics.rate_limiter import RateLimiterBackend

_SECONDS_PER_MINUTE = 60


class DynamoDBRateLimiter(RateLimiterBackend):
    """DynamoDB-backed rate limiter using atomic counter increments.

    Each ``acquire()`` call performs two ``UpdateItem`` operations (1 WCU each)
    for the per-minute and daily counters.  Counters auto-expire via DynamoDB TTL:
    - Minute counters: TTL = 2 minutes
    - Daily counters:  TTL = 25 hours
    """

    def __init__(
        self,
        table_name: str,
        region: str = "ap-northeast-1",
        endpoint_url: str = "",
        max_per_minute: int = 15,
        daily_budget: int = 500,
    ) -> None:
        self._table_name = table_name
        self._region = region
        self._endpoint_url = endpoint_url
        self._max_per_minute = max_per_minute
        self._daily_budget = daily_budget
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
            raise RateLimitError() from exc

    async def acquire(self) -> None:
        """Record a request if within limits, otherwise raise."""
        if self._table is None:
            raise RateLimitError()

        now = datetime.now(tz=UTC)
        minute_key = now.strftime("%Y-%m-%dT%H:%M")
        day_key = now.strftime("%Y-%m-%d")

        # --- daily check (atomic increment + condition) ---
        try:
            self._table.update_item(
                Key={"PK": "RATELIMIT#DAILY", "SK": day_key},
                UpdateExpression="ADD #c :inc SET #t = if_not_exists(#t, :ttl)",
                ConditionExpression=(
                    Attr("count").not_exists() | Attr("count").lt(self._daily_budget)
                ),
                ExpressionAttributeNames={"#c": "count", "#t": "ttl"},
                ExpressionAttributeValues={
                    ":inc": 1,
                    ":ttl": int(time.time()) + 90000,  # 25 hours
                },
            )
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code == "ConditionalCheckFailedException":
                raise BudgetExhaustedError(daily_limit=self._daily_budget) from exc
            raise

        # --- per-minute check (atomic increment + condition) ---
        try:
            self._table.update_item(
                Key={"PK": "RATELIMIT#MINUTE", "SK": minute_key},
                UpdateExpression="ADD #c :inc SET #t = if_not_exists(#t, :ttl)",
                ConditionExpression=(
                    Attr("count").not_exists() | Attr("count").lt(self._max_per_minute)
                ),
                ExpressionAttributeNames={"#c": "count", "#t": "ttl"},
                ExpressionAttributeValues={
                    ":inc": 1,
                    ":ttl": int(time.time()) + 120,  # 2 minutes
                },
            )
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code == "ConditionalCheckFailedException":
                raise RateLimitError(
                    retry_after_seconds=_SECONDS_PER_MINUTE,
                    remaining_daily=None,
                ) from exc
            raise

    async def get_usage(self) -> UsageStats:
        """Return current usage statistics by reading counters."""
        if self._table is None:
            return UsageStats(
                daily_budget=self._daily_budget,
                remaining_today=self._daily_budget,
                per_minute_limit=self._max_per_minute,
            )

        now = datetime.now(tz=UTC)
        minute_key = now.strftime("%Y-%m-%dT%H:%M")
        day_key = now.strftime("%Y-%m-%d")

        requests_today = 0
        requests_this_minute = 0

        try:
            resp = self._table.get_item(
                Key={"PK": "RATELIMIT#DAILY", "SK": day_key},
                ConsistentRead=False,
            )
            item: dict[str, Any] | None = resp.get("Item")
            if item:
                requests_today = int(item.get("count", 0))
        except ClientError:
            pass

        try:
            resp = self._table.get_item(
                Key={"PK": "RATELIMIT#MINUTE", "SK": minute_key},
                ConsistentRead=False,
            )
            item = resp.get("Item")
            if item:
                requests_this_minute = int(item.get("count", 0))
        except ClientError:
            pass

        return UsageStats(
            requests_today=requests_today,
            daily_budget=self._daily_budget,
            remaining_today=max(0, self._daily_budget - requests_today),
            requests_this_minute=requests_this_minute,
            per_minute_limit=self._max_per_minute,
        )

    async def close(self) -> None:
        """No-op: boto3 resources do not require explicit cleanup."""
        self._table = None
