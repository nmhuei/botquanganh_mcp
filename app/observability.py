"""Bounded, redacted transport evidence for MCP incident correlation."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Iterable

from fastmcp.server.middleware import Middleware

from app.logging_audit import log_audit_event
from app.request_context import request_id


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tool_manifest(tools: Iterable[Any]) -> list[dict[str, Any]]:
    """Normalize public tool metadata before hashing it deterministically."""
    manifest: list[dict[str, Any]] = []
    for tool in tools:
        # FunctionTool includes an executable ``fn`` field, which is neither
        # serializable nor part of the public tools/list response. Hash the
        # SDK's MCP wire representation instead.
        if hasattr(tool, "to_mcp_tool"):
            item = tool.to_mcp_tool().model_dump(mode="json", exclude_none=True)
        elif hasattr(tool, "model_dump"):
            item = tool.model_dump(mode="json", exclude_none=True)
        elif isinstance(tool, dict):
            item = tool
        else:
            item = {"name": getattr(tool, "name", str(tool))}
        manifest.append(item)
    return sorted(manifest, key=lambda item: str(item.get("name", "")))


def tool_catalog_sha256(tools: Iterable[Any]) -> str:
    """Hash the public tools/list representation without logging schemas verbatim."""
    encoded = json.dumps(
        _tool_manifest(tools),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class TransportObservability:
    """Thread-safe, bounded state for /debug/transport and health evidence."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._http_requests = 0
        self._mcp_messages = 0
        self._tool_calls = 0
        self._tool_errors = 0
        self._incomplete_responses = 0
        self._client_disconnects = 0
        self._tool_durations_ms = deque(maxlen=1000)
        self._last_mcp_request: dict[str, Any] | None = None
        self._last_tool_call: dict[str, Any] | None = None
        self._catalog_hash = ""
        self._catalog_tool_count = 0

    def record_http_request(self) -> None:
        with self._lock:
            self._http_requests += 1

    def record_incomplete_response(self, *, client_disconnected: bool) -> None:
        with self._lock:
            self._incomplete_responses += 1
            if client_disconnected:
                self._client_disconnects += 1

    def record_mcp_message(self, method: str | None, message_type: str) -> None:
        record = {
            "request_id": request_id() or None,
            "method": method or "unknown",
            "type": message_type,
            "timestamp": _utc_now(),
        }
        with self._lock:
            self._mcp_messages += 1
            self._last_mcp_request = record

    def record_tool_started(self, tool_name: str) -> None:
        record = {
            "request_id": request_id() or None,
            "tool": tool_name,
            "started_at": _utc_now(),
        }
        with self._lock:
            self._tool_calls += 1
            self._last_tool_call = record

    def record_tool_completed(
        self, tool_name: str, duration_ms: float, *, error: bool
    ) -> None:
        record = {
            "request_id": request_id() or None,
            "tool": tool_name,
            "duration_ms": round(max(0.0, duration_ms), 1),
            "error": error,
            "completed_at": _utc_now(),
        }
        with self._lock:
            if error:
                self._tool_errors += 1
            self._tool_durations_ms.append(max(0.0, duration_ms))
            self._last_tool_call = record

    def record_catalog(self, catalog_hash: str, tool_count: int) -> None:
        with self._lock:
            self._catalog_hash = catalog_hash
            self._catalog_tool_count = tool_count

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            durations = sorted(self._tool_durations_ms)

            def percentile(percentile_value: float) -> float:
                if not durations:
                    return 0.0
                index = max(0, math.ceil(percentile_value * len(durations)) - 1)
                return round(durations[index], 1)

            return {
                # Explicit names are suitable for dashboards and incident notes.
                "mcp_http_requests_total": self._http_requests,
                "mcp_tool_calls_total": self._tool_calls,
                "mcp_tool_errors_total": self._tool_errors,
                "mcp_tool_duration_ms": {
                    "p50": percentile(0.50),
                    "p95": percentile(0.95),
                    "p99": percentile(0.99),
                },
                "mcp_incomplete_responses": self._incomplete_responses,
                "mcp_client_disconnects": self._client_disconnects,
                # Readable aliases are retained for the local debug endpoint.
                "requests": self._http_requests,
                "http_requests": self._http_requests,
                "mcp_messages": self._mcp_messages,
                "tool_calls": self._tool_calls,
                "tool_errors": self._tool_errors,
                "incomplete_responses": self._incomplete_responses,
                "client_disconnects": self._client_disconnects,
                "last_mcp_request": self._last_mcp_request,
                "last_tool_call": self._last_tool_call,
                "catalog_hash": self._catalog_hash or None,
                "catalog_tool_count": self._catalog_tool_count,
            }


transport_observability = TransportObservability()


class MCPForensicsMiddleware(Middleware):
    """Emit correlation events around MCP routing and tool execution.

    This uses FastMCP's public middleware hooks, so it observes every registered
    tool without changing any tool's signature or schema.
    """

    async def on_message(self, context, call_next):
        method = context.method or "unknown"
        transport_observability.record_mcp_message(method, context.type)
        log_audit_event(
            "MCP_MESSAGE_RECEIVED",
            {
                "request_id": request_id() or None,
                "method": method,
                "message_type": context.type,
            },
        )
        try:
            result = await call_next(context)
        except Exception as exc:
            log_audit_event(
                "MCP_MESSAGE_FAILED",
                {
                    "request_id": request_id() or None,
                    "method": method,
                    "error_type": type(exc).__name__,
                },
            )
            raise
        log_audit_event(
            "MCP_MESSAGE_COMPLETED",
            {
                "request_id": request_id() or None,
                "method": method,
            },
        )
        return result

    async def on_call_tool(self, context, call_next):
        tool_name = str(context.message.name)
        started = time.monotonic()
        transport_observability.record_tool_started(tool_name)
        log_audit_event(
            "TOOL_STARTED",
            {"request_id": request_id() or None, "tool": tool_name},
        )
        error = False
        try:
            result = await call_next(context)
            error = bool(
                getattr(result, "is_error", getattr(result, "isError", False))
            )
            return result
        except Exception as exc:
            error = True
            log_audit_event(
                "TOOL_FAILED",
                {
                    "request_id": request_id() or None,
                    "tool": tool_name,
                    "error_type": type(exc).__name__,
                },
            )
            raise
        finally:
            duration_ms = (time.monotonic() - started) * 1000
            transport_observability.record_tool_completed(
                tool_name, duration_ms, error=error
            )
            log_audit_event(
                "TOOL_COMPLETED",
                {
                    "request_id": request_id() or None,
                    "tool": tool_name,
                    "duration_ms": round(duration_ms, 1),
                    "error": error,
                },
            )

    async def on_list_tools(self, context, call_next):
        tools = await call_next(context)
        catalog_hash = tool_catalog_sha256(tools)
        transport_observability.record_catalog(catalog_hash, len(tools))
        log_audit_event(
            "TOOL_CATALOG_LISTED",
            {
                "request_id": request_id() or None,
                "manifest_sha256": catalog_hash,
                "tool_count": len(tools),
            },
        )
        return tools
