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


# --- Patch EventSourceResponse for Cloudflare Tunnel buffering ---
from sse_starlette.sse import EventSourceResponse
_original_sse_init = EventSourceResponse.__init__

def _patched_sse_init(self, content, *args, **kwargs):
    # Wrap content with an async generator that yields a padding comment first
    # to flush intermediate buffers (like Cloudflare) immediately.
    async def wrapped_content():
        yield {"comment": " " * 4096}
        async for item in content:
            yield item

    _original_sse_init(self, wrapped_content(), *args, **kwargs)
    self.headers["Cache-Control"] = "no-cache, no-transform"
    self.headers["X-Accel-Buffering"] = "no"

EventSourceResponse.__init__ = _patched_sse_init


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
    from mcp.server.sse import SseServerTransport
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

    # --- Patch: SseServerTransport sessionless POST handler mapping ---
    original_handle_post_message = SseServerTransport.handle_post_message

    async def patched_handle_post_message(self, scope, receive, send) -> None:
        from urllib.parse import parse_qs, urlencode
        query_string = scope.get("query_string", b"").decode("utf-8")
        params = parse_qs(query_string)
        
        session_id_hex = None
        if "session_id" in params:
            try:
                from uuid import UUID
                target_session_id = UUID(hex=params["session_id"][0])
                if target_session_id in self._read_stream_writers:
                    session_id_hex = params["session_id"][0]
            except Exception:
                pass

        if not session_id_hex:
            active_sessions = list(self._read_stream_writers.keys())
            if active_sessions:
                session_id_hex = active_sessions[-1].hex
                logger.info(f"Mapping POST message (sessionless or inactive session) to active session: {session_id_hex}")
                other_params = {k: v for k, v in params.items() if k != "session_id"}
                other_params["session_id"] = [session_id_hex]
                query_string = urlencode(other_params, doseq=True)
                scope["query_string"] = query_string.encode("utf-8")
            else:
                headers = {k.decode('utf-8', errors='ignore'): v.decode('utf-8', errors='ignore') for k, v in scope.get("headers", [])}
                body_chunks = []
                more_body = True
                while more_body:
                    message = await receive()
                    if message["type"] == "http.request":
                        body_chunks.append(message.get("body", b""))
                        more_body = message.get("more_body", False)
                    else:
                        break
                body_text = b"".join(body_chunks).decode("utf-8", errors="ignore")
                logger.info(f"POST message received but no active SSE session found. Headers: {headers}, Body: {body_text}")
                
                from starlette.responses import Response
                response = Response("Accepted", status_code=202)
                await response(scope, receive, send)
                return
                
        await original_handle_post_message(self, scope, receive, send)

    SseServerTransport.handle_post_message = patched_handle_post_message
except ImportError:
    pass

# --- Patch: Allow any Content-Type/Accept for POST requests (ChatGPT compatibility) ---
try:
    from mcp.server.transport_security import TransportSecurityMiddleware
    TransportSecurityMiddleware._validate_content_type = lambda self, content_type: True
except ImportError:
    pass

try:
    from mcp.server.streamable_http import StreamableHTTPServerTransport
    StreamableHTTPServerTransport._check_content_type = lambda self, request: True

    def _compat_accept_headers(self, request):
        accept_header = request.headers.get("accept", "")
        if not accept_header or accept_header.strip() == "*/*":
            return True, True

        accept_types = [media_type.strip() for media_type in accept_header.split(",")]
        has_json = any(media_type.startswith("application/json") for media_type in accept_types)
        has_sse = any(media_type.startswith("text/event-stream") for media_type in accept_types)

        if has_json or has_sse:
            return True, True
        return has_json, has_sse

    StreamableHTTPServerTransport._check_accept_headers = _compat_accept_headers
except ImportError:
    pass


# --- Patch: StreamableHTTPSessionManager sessionless request mapping ---
try:
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    _original_handle_stateful = StreamableHTTPSessionManager._handle_stateful_request

    async def _patched_handle_stateful(self, scope, receive, send) -> None:
        from starlette.requests import Request
        MCP_SESSION_ID_HEADER = "mcp-session-id"
        
        # Pre-parse the request to check headers
        request = Request(scope, receive)
        session_id = request.headers.get(MCP_SESSION_ID_HEADER)
        
        if session_id is None:
            active_sessions = list(self._server_instances.keys())
            if active_sessions:
                mapped_session_id = active_sessions[-1]
                logger.info(f"Mapping sessionless HTTP request to active session: {mapped_session_id}")
                
                # Inject the header into scope["headers"]
                headers = scope.get("headers", [])
                header_name = MCP_SESSION_ID_HEADER.encode("utf-8").lower()
                header_val = mapped_session_id.encode("utf-8")
                
                headers = [h for h in headers if h[0].lower() != header_name]
                headers.append((header_name, header_val))
                scope["headers"] = headers
                
        await _original_handle_stateful(self, scope, receive, send)

    StreamableHTTPSessionManager._handle_stateful_request = _patched_handle_stateful
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
from starlette.routing import Mount


class McpAsgiDispatcher:
    def __init__(self, sse_get_app, sse_post_app, prefix="/mcp"):
        self.sse_get_app = sse_get_app
        self.sse_post_app = sse_post_app
        self.prefix = prefix
        
    async def __call__(self, scope, receive, send):
        if scope.get("method") == "GET":
            await self.sse_get_app(scope, receive, send)
        elif scope.get("method") == "POST":
            # Strip prefix just like Mount does
            original_path = scope.get("path", "")
            original_raw_path = scope.get("raw_path", b"")
            original_query_string = scope.get("query_string", b"")
            
            if original_path.startswith(self.prefix):
                scope["path"] = original_path[len(self.prefix):]
            if original_raw_path.startswith(self.prefix.encode("ascii")):
                scope["raw_path"] = original_raw_path[len(self.prefix):]
                
            async def wrapped_send(message):
                scope["path"] = original_path
                scope["raw_path"] = original_raw_path
                scope["query_string"] = original_query_string
                await send(message)
                
            try:
                await self.sse_post_app(scope, receive, wrapped_send)
            finally:
                scope["path"] = original_path
                scope["raw_path"] = original_raw_path
                scope["query_string"] = original_query_string


def _patched_http_app(self, *args, **kwargs):
    transport = kwargs.get("transport", "http")
    if transport in ("streamable-http", "http"):
        kwargs["json_response"] = True
    app = _original_http_app(self, *args, **kwargs)

    app.router.routes.insert(
        0,
        Route("/healthz", endpoint=healthz_endpoint, methods=["GET"]),
    )
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(TokenAuthMiddleware)

    # Rationale: SseServerTransport sessionless POST handler mapping + Combine GET & POST Mount
    # is required because ChatGPT does not maintain the SSE session_id parameter across GET and POST.
    if transport == "sse":
        routes = app.router.routes
        get_routes = {r.path: r for r in routes if isinstance(r, Route) and "GET" in r.methods}
        mount_routes = {r.path: r for r in routes if isinstance(r, Mount)}
        
        common_paths = set(get_routes.keys()) & set(mount_routes.keys())
        if common_paths:
            combined_routes = []
            for path in common_paths:
                g_route = get_routes[path]
                m_route = mount_routes[path]
                dispatcher = McpAsgiDispatcher(g_route.app, m_route.app, prefix=path)
                combined_routes.append(Route(path, endpoint=dispatcher, methods=["GET", "POST"]))
                logger.info(f"Combined GET Route and POST Mount for SSE path: {path}")
                
            remaining_routes = [
                r for r in routes 
                if not (
                    (isinstance(r, Route) and r.path in common_paths and "GET" in r.methods) or 
                    (isinstance(r, Mount) and r.path in common_paths)
                )
            ]
            app.router.routes = combined_routes + remaining_routes
            
    return app


FastMCP.http_app = _patched_http_app
mcp = FastMCP("BotQuangAnh Host MCP")
