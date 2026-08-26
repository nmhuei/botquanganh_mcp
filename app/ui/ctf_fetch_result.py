"""MCP App resource for displaying one bounded CTF HTTP fetch result."""

from __future__ import annotations

from pathlib import Path

from fastmcp.apps import AppConfig

from app.mcp_server import mcp

CTF_FETCH_RESULT_WIDGET_URI = "ui://botquanganh/ctf-fetch-result-v1.html"
_WIDGET_FILE = Path(__file__).with_name("ctf_fetch_result.html")


@mcp.resource(
    CTF_FETCH_RESULT_WIDGET_URI,
    name="CTF fetch result widget",
    description="Inline UI for a bounded, read-only CTF URL fetch result.",
    app=AppConfig(prefers_border=True),
)
def ctf_fetch_result_widget() -> str:
    """Return the static MCP App component without external network dependencies."""
    return _WIDGET_FILE.read_text(encoding="utf-8")
