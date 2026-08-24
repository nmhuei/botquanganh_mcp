import asyncio

import app.mcp_server as mcp_server
import app.observability as observability
import app.tools.health  # noqa: F401 - registers health_check for middleware tests
from app.mcp_server import mcp
from app.observability import TransportObservability, tool_catalog_sha256


def test_tool_catalog_hash_is_deterministic_for_public_mcp_manifest():
    async def list_tools():
        return await mcp._list_tools()

    tools = asyncio.run(list_tools())
    assert tool_catalog_sha256(tools) == tool_catalog_sha256(reversed(tools))
    assert len(tool_catalog_sha256(tools)) == 64


def test_tool_call_emits_start_completion_and_message_events(monkeypatch):
    events = []
    tracker = TransportObservability()
    monkeypatch.setattr(observability, "transport_observability", tracker)
    monkeypatch.setattr(
        observability,
        "log_audit_event",
        lambda event_type, details: events.append((event_type, details)),
    )

    result = asyncio.run(mcp.call_tool("health_check", {}))

    assert result.is_error is False
    assert [event_type for event_type, _ in events] == [
        "MCP_MESSAGE_RECEIVED",
        "TOOL_STARTED",
        "TOOL_COMPLETED",
        "MCP_MESSAGE_COMPLETED",
    ]
    snapshot = tracker.snapshot()
    assert snapshot["tool_calls"] == 1
    assert snapshot["tool_errors"] == 0
    assert snapshot["last_tool_call"]["tool"] == "health_check"


def test_http_forensics_adds_request_id_and_safe_correlation_fields(monkeypatch):
    events = []
    tracker = TransportObservability()
    monkeypatch.setattr(mcp_server, "transport_observability", tracker)
    monkeypatch.setattr(
        mcp_server,
        "log_audit_event",
        lambda event_type, details: events.append((event_type, details)),
    )
    sent = []

    async def app(_scope, _receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "client": ("127.0.0.1", 1234),
        "headers": [
            (b"x-request-id", b"incident-123"),
            (b"cf-ray", b"cf-ray-123"),
            (b"authorization", b"Bearer must-not-log"),
        ],
    }
    asyncio.run(mcp_server.ForensicsHTTPMiddleware(app)(scope, receive, send))

    start_headers = dict(sent[0]["headers"])
    assert start_headers[b"x-request-id"] == b"incident-123"
    assert [event_type for event_type, _ in events] == [
        "HTTP_REQUEST_RECEIVED",
        "HTTP_RESPONSE_SENT",
    ]
    received = events[0][1]
    assert received["request_id"] == "incident-123"
    assert received["cf_ray"] == "cf-ray-123"
    assert "authorization" not in received
    assert tracker.snapshot()["http_requests"] == 1


def test_debug_transport_rejects_proxy_and_non_loopback_requests():
    async def downstream(_scope, _receive, _send):
        raise AssertionError("debug request must not reach downstream")

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def invoke(client, headers=()):
        sent = []

        async def send(message):
            sent.append(message)

        scope = {
            "type": "http",
            "path": "/debug/transport",
            "client": client,
            "headers": list(headers),
        }
        await mcp_server.LocalDebugMiddleware(downstream)(scope, receive, send)
        return sent

    remote = asyncio.run(invoke(("203.0.113.7", 1)))
    proxied = asyncio.run(
        invoke(("127.0.0.1", 1), ((b"cf-connecting-ip", b"203.0.113.7"),))
    )
    assert remote[0]["status"] == 404
    assert proxied[0]["status"] == 404
