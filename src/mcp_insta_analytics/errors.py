"""Structured error hierarchy for Instagram Analytics MCP server."""

from __future__ import annotations


class InstaAnalyticsError(Exception):
    """Base error for all Instagram Analytics errors."""

    def __init__(self, message: str, *, recovery: str | None = None):
        self.recovery = recovery
        super().__init__(message)

    def to_dict(self) -> dict[str, str]:
        result = {"error": type(self).__name__, "message": str(self)}
        if self.recovery:
            result["recovery"] = self.recovery
        return result


class AuthenticationError(InstaAnalyticsError):
    """Authentication failed or session expired."""

    def __init__(self, message: str = "Authentication failed", *, recovery: str | None = None):
        super().__init__(
            message,
            recovery=recovery
            or (
                "Check INSTA_ANALYTICS_SESSION_COOKIE in .env, "
                "or remove it to use public-only mode."
            ),
        )


class RateLimitError(InstaAnalyticsError):
    """Per-minute rate limit exceeded."""

    def __init__(self, retry_after_seconds: int = 60, remaining_daily: int | None = None):
        self.retry_after_seconds = retry_after_seconds
        self.remaining_daily = remaining_daily
        msg = f"Rate limit exceeded. Retry after {retry_after_seconds}s."
        if remaining_daily is not None:
            msg += f" Daily budget remaining: {remaining_daily}."
        super().__init__(msg, recovery=f"Wait {retry_after_seconds} seconds before retrying.")


class BudgetExhaustedError(InstaAnalyticsError):
    """Daily request budget exhausted."""

    def __init__(self, daily_limit: int = 500):
        self.daily_limit = daily_limit
        super().__init__(
            f"Daily request budget of {daily_limit} exhausted.",
            recovery="Wait until the next day or increase INSTA_ANALYTICS_DAILY_REQUEST_BUDGET.",
        )


class FetcherError(InstaAnalyticsError):
    """Error during data fetching."""

    def __init__(self, message: str = "Data fetch failed", *, recovery: str | None = None):
        super().__init__(
            message,
            recovery=recovery or "Retry the request or check the fetcher backend status.",
        )


class CacheError(InstaAnalyticsError):
    """Cache operation failed."""

    def __init__(self, message: str = "Cache operation failed"):
        super().__init__(message, recovery="Check cache database path and permissions.")


class ConfigError(InstaAnalyticsError):
    """Configuration error."""

    def __init__(self, message: str = "Invalid configuration"):
        super().__init__(message, recovery="Review .env file and environment variables.")
