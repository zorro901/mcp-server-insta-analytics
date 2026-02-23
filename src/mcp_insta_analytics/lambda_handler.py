"""AWS Lambda handler using Mangum to bridge ASGI."""

from __future__ import annotations

from mangum import Mangum

from mcp_insta_analytics.server import mcp

app = mcp.http_app(stateless_http=True)
handler = Mangum(app, lifespan="off")
