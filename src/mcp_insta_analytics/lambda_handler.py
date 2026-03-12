"""AWS Lambda handler using Mangum to bridge ASGI."""

from __future__ import annotations

import os
from typing import Any

from mangum import Mangum

from mcp_insta_analytics.server import mcp

_api_key = os.environ.get("INSTA_ANALYTICS_API_KEY", "")


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Lambda entry point with optional Bearer token check."""
    if _api_key:
        headers: dict[str, str] = event.get("headers") or {}
        if headers.get("authorization", "") != f"Bearer {_api_key}":
            return {"statusCode": 403, "body": "Forbidden"}

    # Create fresh ASGI app + Mangum per invocation to avoid
    # StreamableHTTPSessionManager "can only run once" error on warm Lambda.
    app = mcp.http_app(stateless_http=True)
    mangum_handler = Mangum(app, lifespan="auto")
    return mangum_handler(event, context)  # type: ignore[return-value]
