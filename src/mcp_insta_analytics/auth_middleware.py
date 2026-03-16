"""Bearer token authentication middleware for Starlette/ASGI."""

from __future__ import annotations

import hmac

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class BearerAuthMiddleware:
    """Reject requests that lack a valid ``Authorization: Bearer <token>`` header.

    If *api_key* is empty the middleware is a no-op (all requests pass through).
    Only protects the ``/mcp`` endpoint; other paths (e.g. OAuth discovery
    endpoints like ``/.well-known/*``) are passed through unguarded.
    """

    def __init__(self, app: ASGIApp, *, api_key: str) -> None:
        self.app = app
        self._api_key = api_key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._api_key:
            await self.app(scope, receive, send)
            return

        # Only guard the MCP endpoint itself
        path = scope.get("path", "")
        if path != "/mcp":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        auth_header = request.headers.get("authorization", "")

        if not auth_header.startswith("Bearer "):
            response = JSONResponse(
                {"error": "Missing Authorization header"}, status_code=401
            )
            await response(scope, receive, send)
            return

        token = auth_header[7:]
        if not hmac.compare_digest(token, self._api_key):
            response = JSONResponse(
                {"error": "Invalid API key"}, status_code=403
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
