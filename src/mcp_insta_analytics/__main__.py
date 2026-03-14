"""Entry point for running the MCP server: python -m mcp_insta_analytics"""

import sys

from starlette.middleware import Middleware

from mcp_insta_analytics.auth_middleware import BearerAuthMiddleware
from mcp_insta_analytics.config import Settings
from mcp_insta_analytics.server import mcp

config = Settings()

if "--http" in sys.argv:
    middleware: list[Middleware] = []
    if config.api_key:
        middleware.append(Middleware(BearerAuthMiddleware, api_key=config.api_key))  # type: ignore[arg-type]

    mcp.run(
        transport="streamable-http",
        host=config.server_host,
        port=config.server_port,
        middleware=middleware,
    )
else:
    mcp.run()
