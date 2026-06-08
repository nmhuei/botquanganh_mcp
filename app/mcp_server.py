import logging

from fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from starlette.routing import Route, Mount

# Set up logging
logger = logging.getLogger("fallback_runner_audit")

# FASTMCP Compatibility Version check
FASTMCP_COMPAT_VERSION = "3.4.0"

import fastmcp
if getattr(fastmcp, "__version__", "") != FASTMCP_COMPAT_VERSION:
    logger.warning(
        f"Warning: FastMCP version '{getattr(fastmcp, '__version__', 'unknown')}' does not match "
        f"tested compatibility version '{FASTMCP_COMPAT_VERSION}'. Patches may fail or behave unexpectedly."
    )

class TokenAuthMiddleware:
    """ASGI Middleware to enforce GATEWAY_TOKEN authentication for HTTP and WebSocket requests in non-stdio transports."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if path.startswith("/events/"):
            await self.app(scope, receive, send)
            return

        if scope.get("type") in ("http", "websocket"):
            # Extract headers
            headers = {}
            for k, v in scope.get("headers", []):
                headers[k.decode("latin-1").lower()] = v.decode("latin-1")
            
            # Try getting token from different sources:
            # 1. Authorization header: "Bearer <token>" or "<token>"
            # 2. X-Gateway-Token header: "<token>"
            token = ""
            auth_header = headers.get("authorization", "")
            if auth_header:
                if auth_header.lower().startswith("bearer "):
                    token = auth_header[7:]
                else:
                    token = auth_header
            
            if not token:
                token = headers.get("x-gateway-token", "")
            
            from app.auth import verify_token
            if not verify_token(token):
                logger.warning("Unauthorized access attempt rejected (invalid or missing token).")
                from starlette.responses import Response
                response = Response("Unauthorized: Invalid or missing token.", status_code=401)
                await response(scope, receive, send)
                return
                
        await self.app(scope, receive, send)

# --- Patch 0: Allow any Content-Type for POST requests (ChatGPT compatibility) ---
# Rationale: ChatGPT web interface often sends JSON-RPC requests with non-standard or missing Content-Type headers.
# This patch overrides TransportSecurityMiddleware._validate_content_type to prevent returning 415 Unsupported Media Type.
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

        accept_types = [media_type.strip() for media_type in accept_header.split(",")]
        has_json = any(media_type.startswith("application/json") for media_type in accept_types)
        has_sse = any(media_type.startswith("text/event-stream") for media_type in accept_types)

        if has_json or has_sse:
            return True, True
        return has_json, has_sse

    StreamableHTTPServerTransport._check_accept_headers = _compat_accept_headers

    _original_jsonrpc_model_validate = JSONRPCMessage.model_validate

    @classmethod
    def _compat_jsonrpc_model_validate(cls, obj, *args, **kwargs):
        if isinstance(obj, dict) and obj.get("method") == "initialize":
            params = obj.get("params")
            if not isinstance(params, dict):
                obj = dict(obj)
                obj["params"] = {"capabilities": {}}
            elif "capabilities" not in params:
                obj = dict(obj)
                obj["params"] = {**params, "capabilities": {}}
        return _original_jsonrpc_model_validate(obj, *args, **kwargs)

    JSONRPCMessage.model_validate = _compat_jsonrpc_model_validate
except ImportError:
    pass


# --- Patch 1: SseServerTransport sessionless POST handler mapping ---
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


# --- Patch 2: Combine GET Route & POST Mount for SSE path to prevent 405 Method Not Allowed ---
original_http_app = FastMCP.http_app


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

def patched_http_app(self, *args, **kwargs):
    app = original_http_app(self, *args, **kwargs)
    transport = kwargs.get("transport", "http")

    # Inject SSE events route
    from app.sse_events import sse_route
    app.router.routes.append(sse_route)

    # Add Token Authentication Middleware to the ASGI app
    app.add_middleware(TokenAuthMiddleware)

    # We only customize the routes if the transport is "sse"
    # Rationale: SseServerTransport sessionless POST handler mapping + Combine GET & POST Mount
    # is required because ChatGPT does not maintain the SSE session_id parameter across GET and POST.
    # We combine GET Route and POST Mount to avoid 405 Method Not Allowed when route resolving.
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

FastMCP.http_app = patched_http_app

# Initialize FastMCP server
mcp = FastMCP("Fallback Runner MCP")
