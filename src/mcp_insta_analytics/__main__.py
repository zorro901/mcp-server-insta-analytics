"""Entry point for running the MCP server: python -m mcp_insta_analytics"""

import sys

from mcp_insta_analytics.config import Settings
from mcp_insta_analytics.server import mcp

config = Settings()

if "--http" in sys.argv:
    mcp.run(
        transport="streamable-http",
        host=config.server_host,
        port=config.server_port,
    )
else:
    mcp.run()
