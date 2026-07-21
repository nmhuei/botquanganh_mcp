import asyncio
import json

import app.mcp_server as mcp_server
from app.metrics import MetricsTracker
from app.ratelimit import rate_limiter


def test_rate_limit_rejection_is_observed_by_outer_metrics(monkeypatch):
    downstream_called = False
    sent = []

    async def downstream(scope, receive, send):
        nonlocal downstream_called
        downstream_called = True

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    monkeypatch.setattr(rate_limiter, "is_allowed", lambda _ip: (False, 3))
    tracker = MetricsTracker()
    monkeypatch.setattr(mcp_server, "metrics", tracker)

    scope = {
        "type": "http",
        "path": "/api/v1/health",
        "headers": [],
        "client": ("127.0.0.1", 12345),
    }
    app = mcp_server.MetricsMiddleware(mcp_server.TokenAuthMiddleware(downstream))
    asyncio.run(app(scope, receive, send))

    assert downstream_called is False
    response_start = next(
        message for message in sent if message["type"] == "http.response.start"
    )
    assert response_start["status"] == 429
    body_message = next(
        message for message in sent if message["type"] == "http.response.body"
    )
    body = json.loads(body_message["body"])
    assert body["error"]["code"] == "RATE_LIMITED"
    assert body["error"]["retry_after"] == 3

    stats = tracker.get_stats()
    assert stats["total_requests"] == 1
    assert stats["rate_limit_hits"] == 1
    assert stats["client_error_count"] == 1
    assert stats["status_counts"] == {"429": 1}
    assert stats["in_flight"] == 0
