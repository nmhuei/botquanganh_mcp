import logging
import time
from ipaddress import ip_address

import fastmcp
from fastmcp import FastMCP
from starlette.requests import Request
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
from app.logging_audit import log_audit_event
from app.metrics import metrics
from app.observability import MCPForensicsMiddleware, transport_observability
from app.request_context import (
    new_request_id,
    reset_request_context,
    set_request_context,
)

logger = logging.getLogger("botquanganh_host_mcp")
FASTMCP_COMPAT_VERSION = "3.4.0"

if getattr(fastmcp, "__version__", "") != FASTMCP_COMPAT_VERSION:
    logger.warning(
        "FastMCP version %s differs from tested version %s.",
        getattr(fastmcp, "__version__", "unknown"),
        FASTMCP_COMPAT_VERSION,
    )


class TokenAuthMiddleware:
    """Apply gateway-token authentication and origin validation."""

    def __init__(self, app):
        self.app = app

    @staticmethod
    def _is_allowed_origin(origin: str, host: str) -> bool:
        from app.config import ALLOWED_ORIGINS

        if not origin:
            return True
        origin_clean = origin.strip().lower()
        if ALLOWED_ORIGINS:
            return any(
                origin_clean == allowed.lower()
                or origin_clean.endswith("." + allowed.lower())
                for allowed in ALLOWED_ORIGINS
            )
        # Default allow list: loopback, trycloudflare.com, chatgpt.com, openai.com, or matching Host
        if (
            origin_clean.startswith("http://localhost:")
            or origin_clean.startswith("https://localhost:")
            or origin_clean.startswith("http://127.0.0.1:")
            or origin_clean.startswith("https://127.0.0.1:")
            or origin_clean in {"http://localhost", "https://localhost", "http://127.0.0.1", "https://127.0.0.1"}
            or origin_clean.endswith(".trycloudflare.com")
            or origin_clean in {"https://chatgpt.com", "https://chat.openai.com"}
            or origin_clean.endswith(".chatgpt.com")
            or origin_clean.endswith(".openai.com")
        ):
            return True
        if host and (
            origin_clean == f"http://{host.lower()}"
            or origin_clean == f"https://{host.lower()}"
        ):
            return True
        return False

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
            origin = headers.get("origin", "")
            host = headers.get("host", "")
            if origin and not self._is_allowed_origin(origin, host):
                response = JSONResponse(
                    format_error_code(
                        "FORBIDDEN_ORIGIN",
                        message=f"Origin '{origin}' is not authorized.",
                    ),
                    status_code=403,
                )
                await response(scope, receive, send)
                return

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


def _headers(scope) -> dict[str, str]:
    return {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in scope.get("headers", [])
    }


def _is_loopback(host: str) -> bool:
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


async def debug_transport_endpoint(_request: Request) -> JSONResponse:
    """Return bounded transport metadata only; no payloads, secrets, or paths."""
    snapshot = transport_observability.snapshot()
    return JSONResponse(
        {
            "server": "ok",
            "version": VERSION,
            "fastmcp": getattr(fastmcp, "__version__", "unknown"),
            "stateless": MCP_STATELESS_HTTP,
            **snapshot,
        }
    )


class LocalDebugMiddleware:
    """Keep transport diagnostics on a direct loopback connection only."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("path") != "/debug/transport":
            await self.app(scope, receive, send)
            return

        headers = _headers(scope)
        client = scope.get("client") or ("", 0)
        # A request via Cloudflare carries proxy headers even though cloudflared
        # reaches the origin from 127.0.0.1. Reject it so this route remains a
        # direct local diagnostic, not a public tunnel endpoint.
        is_direct = not any(
            headers.get(name)
            for name in ("cf-connecting-ip", "x-forwarded-for", "x-real-ip")
        )
        if not _is_loopback(str(client[0])) or not is_direct:
            response = JSONResponse({"detail": "Not found."}, status_code=404)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


class ForensicsHTTPMiddleware:
    """Correlate each HTTP request with the FastMCP middleware evidence chain."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = _headers(scope)
        path = str(scope.get("path", "unknown"))
        client = scope.get("client") or ("", 0)
        client_host = str(client[0])
        request_id = new_request_id(headers.get("x-request-id"))
        started = time.monotonic()
        status_code = 500
        response_bytes = 0
        response_complete = False
        client_disconnected = False
        tokens = set_request_context(
            request_id, path=path, client_host=client_host
        )
        transport_observability.record_http_request()
        log_audit_event(
            "HTTP_REQUEST_RECEIVED",
            {
                "request_id": request_id,
                "method": scope.get("method", "unknown"),
                "path": path,
                "client_host": client_host,
                "cf_ray": headers.get("cf-ray"),
                "mcp_protocol_version": headers.get("mcp-protocol-version"),
                "mcp_method": headers.get("mcp-method"),
                "mcp_name": headers.get("mcp-name"),
            },
        )

        async def wrapped_receive():
            nonlocal client_disconnected
            message = await receive()
            if message.get("type") == "http.disconnect":
                client_disconnected = True
            return message

        async def wrapped_send(message):
            nonlocal status_code, response_bytes, response_complete
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 0) or 500)
                response_headers = list(message.get("headers", []))
                if not any(key.lower() == b"x-request-id" for key, _ in response_headers):
                    response_headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = response_headers
            elif message.get("type") == "http.response.body":
                response_bytes += len(message.get("body", b""))
                if not message.get("more_body", False):
                    response_complete = True
            await send(message)

        try:
            await self.app(scope, wrapped_receive, wrapped_send)
        except Exception as exc:
            log_audit_event(
                "HTTP_REQUEST_FAILED",
                {
                    "request_id": request_id,
                    "path": path,
                    "error_type": type(exc).__name__,
                },
            )
            raise
        finally:
            duration_ms = (time.monotonic() - started) * 1000
            incomplete = not response_complete
            if incomplete:
                transport_observability.record_incomplete_response(
                    client_disconnected=client_disconnected
                )
            log_audit_event(
                "HTTP_RESPONSE_SENT" if not incomplete else "HTTP_RESPONSE_INCOMPLETE",
                {
                    "request_id": request_id,
                    "path": path,
                    "status": status_code,
                    "duration_ms": round(duration_ms, 1),
                    "response_bytes": response_bytes,
                    "client_disconnected": client_disconnected,
                },
            )
            reset_request_context(tokens)


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
        response_bytes = 0
        response_complete = False
        client_disconnected = False
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
                response_bytes=response_bytes,
                incomplete=not response_complete,
                client_disconnected=client_disconnected,
            )

        async def wrapped_send(message):
            nonlocal status_code, response_bytes, response_complete
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 0) or 500)
            if message.get("type") == "http.response.body":
                response_bytes += len(message.get("body", b""))
                if not message.get("more_body", False):
                    response_complete = True
            await send(message)
            if (
                message.get("type") == "http.response.body"
                and not message.get("more_body", False)
            ):
                finish_once()

        async def wrapped_receive():
            nonlocal client_disconnected
            message = await receive()
            if message.get("type") == "http.disconnect":
                client_disconnected = True
            return message

        try:
            await self.app(scope, wrapped_receive, wrapped_send)
        except Exception:
            status_code = 500
            raise
        finally:
            finish_once()


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
    if not any(
        getattr(route, "path", None) == "/debug/transport"
        for route in app.router.routes
    ):
        app.router.routes.insert(
            1,
            Route("/debug/transport", endpoint=debug_transport_endpoint, methods=["GET"]),
        )

    from app.rest_api import install_rest_routes

    install_rest_routes(app)
    # Starlette wraps middleware in reverse order. Metrics stays outermost for
    # every response; Forensics binds a request id before FastMCP dispatch; the
    # local-only guard prevents Cloudflare from exposing /debug/transport.
    app.add_middleware(TokenAuthMiddleware)
    app.add_middleware(LocalDebugMiddleware)
    app.add_middleware(ForensicsHTTPMiddleware)
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
mcp.add_middleware(MCPForensicsMiddleware())
