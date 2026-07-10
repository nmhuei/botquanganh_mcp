import logging
import time

import fastmcp
from fastmcp import FastMCP
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from app.config import TRUST_PROXY_HEADERS
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
            token = auth_header[7:] if auth_header.lower().startswith("bearer ") else auth_header
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


# ChatGPT clients may omit or loosen HTTP content negotiation headers.
from mcp.server.transport_security import TransportSecurityMiddleware

TransportSecurityMiddleware._validate_content_type = lambda self, content_type: True

try:
    from mcp.server.streamable_http import StreamableHTTPServerTransport
    from mcp.types import JSONRPCMessage

    StreamableHTTPServerTransport._check_content_type = lambda self, request: True

    def _compat_accept_headers(self, request):
        accept_header = request.headers.get("accept", "")
        if not accept_header or accept_header.strip() == "*/*":
            return True, True
        accepted = [item.strip() for item in accept_header.split(",")]
        has_json = any(item.startswith("application/json") for item in accepted)
        has_sse = any(item.startswith("text/event-stream") for item in accepted)
        return (True, True) if has_json or has_sse else (False, False)

    StreamableHTTPServerTransport._check_accept_headers = _compat_accept_headers

    _original_validate = JSONRPCMessage.model_validate

    @classmethod
    def _compat_jsonrpc_validate(cls, obj, *args, **kwargs):
        if isinstance(obj, dict) and obj.get("method") == "initialize":
            params = obj.get("params")
            if not isinstance(params, dict):
                obj = {**obj, "params": {"capabilities": {}}}
            elif "capabilities" not in params:
                obj = {**obj, "params": {**params, "capabilities": {}}}
        return _original_validate(obj, *args, **kwargs)

    JSONRPCMessage.model_validate = _compat_jsonrpc_validate
except ImportError:
    pass


async def healthz_endpoint(_request):
    return PlainTextResponse("OK", status_code=200)


class MetricsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        started = time.monotonic()
        path = scope.get("path", "unknown")

        async def wrapped_send(message):
            if message.get("type") == "http.response.start":
                latency_ms = (time.monotonic() - started) * 1000
                metrics.record_request(path, latency_ms, message.get("status", 0))
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        except Exception:
            metrics.record_request(path, (time.monotonic() - started) * 1000, 500)
            raise


_original_http_app = FastMCP.http_app


def _patched_http_app(self, *args, **kwargs):
    app = _original_http_app(self, *args, **kwargs)
    app.router.routes.insert(
        0,
        Route("/healthz", endpoint=healthz_endpoint, methods=["GET"]),
    )
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(TokenAuthMiddleware)
    return app


FastMCP.http_app = _patched_http_app
mcp = FastMCP("BotQuangAnh Host MCP")
