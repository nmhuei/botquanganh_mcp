"""Unified server information tool: system capability bootstrap, operational limits, and sandbox telemetry.

Consolidates server health and capability discovery into an evolved super-tool.
Exempt from pre-flight workspace binding to allow agents and UI clients to bootstrap
and discover the environment, limits, and the ~/Downloads/bqa-trash sandbox.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import app.config
from app.mcp_server import mcp
from app.metrics import metrics
from app.tools_common import (
    _guard_chat_id,
    _record_tool_call,
    enforce_bridge_payload_limit,
)

SUPER_TOOLS_MANIFEST = [
    {
        "name": "workspace_explore",
        "role": "Directory tree inspection & chunked file reading with binary guards",
    },
    {
        "name": "workspace_edit",
        "role": "Atomic writes, appends, and anchor-verified replacements with AST validation",
    },
    {
        "name": "workspace_search",
        "role": "Ripgrep-powered regex content search & file path globbing",
    },
    {
        "name": "terminal_execute",
        "role": "Unrestricted shell execution with process-group isolation and timeout kill",
    },
    {
        "name": "task",
        "role": "Task lifecycle management with wait, tail, kill, list, and status actions",
    },
    {
        "name": "web_intelligence",
        "role": "Open HTTP/HTTPS recon with clean text parsing, comments, and CTF flag detection",
    },
    {
        "name": "server_info",
        "role": "System status bootstrap, operational limits, and bqa-trash sandbox location",
    },
    {
        "name": "workspace_context",
        "role": "Attribution gateway, state persistence, hypotheses matrix, and resume briefing",
    },
]


def health_check() -> dict[str, Any]:
    """Non-MCP health compatibility helper backed by the server info surface."""
    return {"ok": True, "service": getattr(app.config, "SERVICE_NAME", "botquanganh-host-mcp"), "tools": [item["name"] for item in SUPER_TOOLS_MANIFEST]}


def get_capabilities() -> dict[str, Any]:
    """Non-MCP capability helper backed by the eight-tool manifest."""
    return {"ok": True, "tools": [item["name"] for item in SUPER_TOOLS_MANIFEST]}


@mcp.tool(
    name="server_info",
    description=(
        "Unified server discovery super-tool. Returns server status, operational limits, "
        "the ~/Downloads/bqa-trash sandbox path, and the 8 Super-Tools catalog. "
        "Call this first for basic MCP status. Exempt from pre-flight workspace binding."
    ),
)
def server_info(chat_id: Optional[str] = None) -> dict[str, Any]:
    """Return comprehensive system health, limits, sandbox location, and tool capabilities."""
    validated, rejection = _guard_chat_id("server_info", chat_id)
    if rejection is not None:
        return enforce_bridge_payload_limit(rejection, "server_info")

    try:
        stats = metrics.get_stats()
    except Exception:
        stats = {}

    result = {
        "ok": True,
        "service": getattr(app.config, "SERVICE_NAME", "botquanganh-host-mcp"),
        "version": app.config.VERSION,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "attribution_mode": getattr(app.config, "ATTRIBUTION_MODE", "enforce"),
        "sandbox_trash_dir": str(getattr(app.config, "HOST_TRASH_DIR", "/home/light/Downloads/bqa-trash")),
        "workspace_root": str(getattr(app.config, "HOST_WORKSPACE_DIR", "/home/light")),
        "limits": {
            "max_single_file_bytes": getattr(app.config, "MAX_SINGLE_FILE_BYTES", 30_000_000),
            "max_output_bytes": getattr(app.config, "MAX_OUTPUT_BYTES", 5_000_000),
            "default_timeout_seconds": getattr(app.config, "DEFAULT_TIMEOUT_SECONDS", 60),
            "max_timeout_seconds": getattr(app.config, "MAX_TIMEOUT_SECONDS", 300),
            "max_concurrent_commands": getattr(app.config, "MAX_CONCURRENT_COMMANDS", 100),
        },
        "super_tools": SUPER_TOOLS_MANIFEST,
        "runtime_metrics": stats,
    }

    _record_tool_call("server_info", validated)
    return enforce_bridge_payload_limit(result, "server_info")
