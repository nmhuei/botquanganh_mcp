import logging
import time

import fastmcp
from fastmcp import FastMCP
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from app.config import (
    MCP_JSON_RESPONSE,
    MCP_STATELESS_HTTP,
    TRUST_PROXY_HEADERS,
    VERSION,
)
from app.metrics import metrics
from app.ratelimit import rate_limiter

logger = logging.getLogger("botquanganh_host_mcp")
FASTMCP_COMPAT_VERSION = "3.4.0"

if getattr(fastmcp, "__version__", "") != FASTMCP_COMPAT_VERSION:
    logger.warning(
        "FastMCP version %s differs from tested version %s.",
        getattr(fastmcp, "__version__", "unknown"),
        FASTMCP_COMPAT_VERSION,
    )


class TokenAuthMiddleware:
    """Apply per-IP rate limiting and gateway-token authentication."""

    def __init__(self, app):
        self.app = app

    @staticmethod
    def _get_client_ip(scope: dict) -> str:
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        if TRUST_PROXY_HEADERS:
            forwarded = headers.get("x-forwarded-for", "")
            if forwarded:
                return forwarded.split(",", 1)[0].strip()
        client = scope.get("client")
        return str(client[0]) if client else "unknown"

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if path == "/healthz":
            await self.app(scope, receive, send)
            return

        if scope.get("type") in {"http", "websocket"}:
            client_ip = self._get_client_ip(scope)
            allowed, retry_after = rate_limiter.is_allowed(client_ip)
            if not allowed:
                response = JSONResponse(
                    {"error": "rate_limit_exceeded", "retry_after": retry_after},
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
                await response(scope, receive, send)
                return

            headers = {
                key.decode("latin-1").lower(): value.decode("latin-1")
                for key, value in scope.get("headers", [])
            }
            auth_header = headers.get("authorization", "")
            token = (
                auth_header[7:]
                if auth_header.lower().startswith("bearer ")
                else auth_header
            )
            if not token:
                token = headers.get("x-gateway-token", "")

            from app.auth import verify_token

            if not verify_token(token):
                response = Response(
                    "Unauthorized: invalid or missing token.",
                    status_code=401,
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


async def healthz_endpoint(_request):
    return PlainTextResponse("OK", status_code=200)


class MetricsMiddleware:
    """Record response status and latency without altering the response body."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        started = time.monotonic()
        path = scope.get("path", "unknown")
        response_started = False

        async def wrapped_send(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
                metrics.record_request(
                    path,
                    (time.monotonic() - started) * 1000,
                    message.get("status", 0),
                )
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        except Exception:
            if not response_started:
                metrics.record_request(
                    path,
                    (time.monotonic() - started) * 1000,
                    500,
                )
            raise


_original_http_app = FastMCP.http_app


def _chatgpt_http_app(self, *args, **kwargs):
    """Build a ChatGPT-friendly Streamable HTTP app using public SDK options.

    Stateless HTTP prevents requests from being attached to the wrong session
    when ChatGPT opens concurrent connections. JSON responses avoid keeping an
    SSE stream open for normal request/response tool calls through Cloudflare.
    """

    transport = kwargs.get("transport", "http")
    if transport in {"http", "streamable-http"}:
        # The FastMCP CLI passes explicit False values from its global settings.
        # Force the server-local ChatGPT transport settings instead of using
        # setdefault(), otherwise the CLI silently re-enables stateful SSE.
        kwargs["json_response"] = MCP_JSON_RESPONSE
        kwargs["stateless_http"] = MCP_STATELESS_HTTP

    app = _original_http_app(self, *args, **kwargs)
    if not any(getattr(route, "path", None) == "/healthz" for route in app.router.routes):
        app.router.routes.insert(
            0,
            Route("/healthz", endpoint=healthz_endpoint, methods=["GET"]),
        )
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(TokenAuthMiddleware)
    return app


FastMCP.http_app = _chatgpt_http_app

mcp = FastMCP(
    "BotQuangAnh Host MCP",
    version=VERSION,
    instructions=(
        "Host-only MCP server. Use host_knowledge before unfamiliar host work, "
        "then use the host filesystem and command tools."
    ),
)
