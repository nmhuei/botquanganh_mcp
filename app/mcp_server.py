import logging
import time

import fastmcp
from fastmcp import FastMCP
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from app.config import (
    MCP_JSON_RESPONSE,
    MCP_STATELESS_HTTP,
    TRUST_PROXY_HEADERS,
    VERSION,
    HOST_WORKSPACE_DIR,
    HOST_DEFAULT_DIR,
)
from app.error_contract import format_error_code
from app.metrics import metrics

logger = logging.getLogger("botquanganh_host_mcp")
FASTMCP_COMPAT_VERSION = "3.4.0"

if getattr(fastmcp, "__version__", "") != FASTMCP_COMPAT_VERSION:
    logger.warning(
        "FastMCP version %s differs from tested version %s.",
        getattr(fastmcp, "__version__", "unknown"),
        FASTMCP_COMPAT_VERSION,
    )


class TokenAuthMiddleware:
    """Apply gateway-token authentication."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if path == "/healthz":
            await self.app(scope, receive, send)
            return

        if scope.get("type") in {"http", "websocket"}:

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
                response = JSONResponse(
                    format_error_code(
                        "AUTH_REQUIRED",
                        message="Authentication required.",
                    ),
                    status_code=401,
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


async def healthz_endpoint(_request):
    return PlainTextResponse("OK", status_code=200)


class MetricsMiddleware:
    """Record complete HTTP requests, including auth and rate-limit responses."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        started = time.monotonic()
        path = scope.get("path", "unknown")
        status_code = 500
        finished = False
        metrics.begin_request()

        def finish_once() -> None:
            nonlocal finished
            if finished:
                return
            finished = True
            metrics.record_request(
                path,
                (time.monotonic() - started) * 1000,
                status_code,
            )

        async def wrapped_send(message):
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 0) or 500)
            await send(message)
            if (
                message.get("type") == "http.response.body"
                and not message.get("more_body", False)
            ):
                finish_once()

        try:
            await self.app(scope, receive, wrapped_send)
            finish_once()
        except Exception:
            status_code = 500
            finish_once()
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

    from app.rest_api import install_rest_routes

    install_rest_routes(app)
    # Add auth first, then metrics. Starlette wraps middleware in reverse order,
    # making MetricsMiddleware outermost so 401 and 429 responses are observed.
    app.add_middleware(TokenAuthMiddleware)
    app.add_middleware(MetricsMiddleware)
    return app


FastMCP.http_app = _chatgpt_http_app

mcp = FastMCP(
    "BotQuangAnh Host MCP",
    version=VERSION,
    instructions=(
        "Host-only MCP server. Use host_knowledge before unfamiliar host work, "
        "then use the host filesystem and command tools. "
        f"By default, all operations (files, directories, command executions) "
        f"MUST be relative to or run within the default directory: '{HOST_DEFAULT_DIR}'. "
        f"Operations are allowed and restricted to the workspace boundary: '{HOST_WORKSPACE_DIR}'. "
        "When a user explicitly says an HTTPS CTF URL is authorized and asks for a basic "
        "fetch, use ctf_fetch_url for one read-only GET. Do not scan, fuzz, crawl, or "
        "enumerate unless the user provides explicit scope and limits. After a successful "
        "ctf_fetch_url, use ctf_render_fetch_result with its complete result when an inline "
        "result card would help the user inspect the response."
    ),
)
