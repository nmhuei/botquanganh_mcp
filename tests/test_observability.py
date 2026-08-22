import asyncio
import json
from logging.handlers import RotatingFileHandler

import pytest

import app.auth
import app.logging_audit as audit
import app.mcp_server as mcp_server
from app.metrics import MetricsTracker
from app.tools.health import health_check


def test_metrics_tracker_reports_distribution_and_concurrency():
    tracker = MetricsTracker()
    tracker.begin_request()
    tracker.begin_request()
    tracker.record_request("/ok", 1, 200)
    tracker.record_request("/auth", 2, 401)
    tracker.begin_request()
    tracker.record_request("/limited", 3, 429)
    tracker.begin_request()
    tracker.record_request("/error", 100, 500)

    stats = tracker.get_stats()
    assert stats["total_requests"] == 4
    assert stats["error_count"] == 1
    assert stats["client_error_count"] == 2
    assert stats["auth_failures"] == 1
    assert stats["rate_limit_hits"] == 1
    assert stats["in_flight"] == 0
    assert stats["peak_in_flight"] == 2
    assert stats["avg_latency_ms"] == 26.5
    assert stats["p50_latency_ms"] == 2
    assert stats["p95_latency_ms"] == 100
    assert stats["status_counts"] == {"200": 1, "401": 1, "429": 1, "500": 1}
    assert stats["path_counts"]["/ok"] == 1


def test_auth_failure_is_observed_by_outer_metrics(monkeypatch):
    sent = []

    async def downstream(scope, receive, send):  # pragma: no cover
        raise AssertionError("downstream must not run")

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    monkeypatch.setattr(app.auth, "verify_token", lambda _token: False)
    tracker = MetricsTracker()
    monkeypatch.setattr(mcp_server, "metrics", tracker)

    scope = {
        "type": "http",
        "path": "/api/v1/health",
        "headers": [],
        "client": ("127.0.0.1", 1),
    }
    middleware_app = mcp_server.MetricsMiddleware(
        mcp_server.TokenAuthMiddleware(downstream)
    )
    asyncio.run(middleware_app(scope, receive, send))

    stats = tracker.get_stats()
    assert stats["total_requests"] == 1
    assert stats["auth_failures"] == 1
    assert stats["status_counts"] == {"401": 1}
    assert stats["in_flight"] == 0


def test_health_exposes_extended_metrics():
    metrics = health_check()["metrics"]
    for field in (
        "client_error_count",
        "auth_failures",
        "in_flight",
        "peak_in_flight",
        "p50_latency_ms",
        "p95_latency_ms",
        "status_counts",
        "latency_sample_size",
    ):
        assert field in metrics


def test_audit_redacts_keys_and_inline_secret_values(monkeypatch):
    monkeypatch.setattr(audit, "AUDIT_MAX_FIELD_CHARS", 100)
    private_key = (
        "-----BEGIN " + "PRIVATE KEY-----\nabc\n-----END " + "PRIVATE KEY-----"
    )
    value = {
        "token": "direct-secret",  # pragma: allowlist secret
        "message": (
            "Authorization: Bearer abc.def.ghi "
            "api_key=plain-secret sk-abcdefghijklmnop "
            + private_key
        ),
        "nested": [{"password": "nested-secret"}],  # pragma: allowlist secret
        "long": "x" * 200,
    }
    redacted = audit.redact_sensitive_data(value)
    serialized = json.dumps(redacted)
    for secret in (
        "direct-secret",
        "abc.def.ghi",
        "plain-secret",
        "sk-abcdefghijklmnop",
        private_key,
        "nested-secret",
    ):
        assert secret not in serialized
    assert redacted["long"].endswith("... [TRUNCATED]")


def test_audit_event_has_versioned_schema_and_no_secret(monkeypatch):
    calls = []
    monkeypatch.setattr(audit.logger, "info", lambda *args: calls.append(args))
    audit.log_audit_event(
        "TEST_EVENT",
        {"message": "Bearer top-secret-token", "gateway_token": "hidden"},
    )
    assert len(calls) == 1
    fmt, payload_json = calls[0]
    assert fmt == "AUDIT_EVENT: %s"
    assert "top-secret-token" not in payload_json
    payload = json.loads(payload_json)
    assert payload["schema_version"] == 1
    assert payload["event_type"] == "TEST_EVENT"
    assert payload["service"]
    assert payload["service_version"]
    assert payload["event_id"]
    assert payload["details"]["gateway_token"] == "[REDACTED]"


def test_audit_logger_uses_rotation():
    assert any(isinstance(handler, RotatingFileHandler) for handler in audit.logger.handlers)


def test_audit_log_lookup_includes_rotated_files(tmp_path, monkeypatch):
    log_file = tmp_path / "audit.log"
    log_file.write_text("run-123 current\n", encoding="utf-8")
    (tmp_path / "audit.log.1").write_text("run-123 rotated\n", encoding="utf-8")
    monkeypatch.setattr(audit, "LOG_FILE", log_file)
    monkeypatch.setattr(audit, "AUDIT_LOG_BACKUP_COUNT", 2)
    result = audit.get_audit_logs_for_run("run-123")
    assert "current" in result
    assert "rotated" in result
    with pytest.raises(ValueError):
        audit.get_audit_logs_for_run("bad\nvalue")
