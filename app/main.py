import os
import sys
from app.mcp_server import mcp

# Core tools: lightweight and enough for the MCP server to boot and operate.
import app.tools.health
import app.tools.runs
import app.tools.workspace
from app.config import MCP_BIND_HOST, MCP_PORT, ENABLE_ADVANCED_TOOLS

# Advanced tools: Docker runner/probe/shell features. Enabled after running
# scripts/install_advanced_tools.sh or setting ENABLE_ADVANCED_TOOLS=true.
if ENABLE_ADVANCED_TOOLS:
    import app.tools.fallback
    import app.tools.probe
    import app.tools.shell

from app.logging_audit import log_audit_event

# Log server boot
log_audit_event("SERVER_STARTUP", {
    "host": MCP_BIND_HOST,
    "port": MCP_PORT,
    "pid": os.getpid(),
    "advanced_tools_enabled": ENABLE_ADVANCED_TOOLS,
})

if __name__ == "__main__":
    # Check if run with specific transport options or default to stdio
    # FastMCP run() detects arguments or runs via stdio.
    # Typically, running FastMCP:
    # python3 -m app.main
    # will run it in stdio mode which is perfect for most MCP clients.
    # To run as SSE server, it's typically: fastmcp run app/main.py
    # or mcp.run(transport="sse", host=MCP_BIND_HOST, port=MCP_PORT)
    # Let's default to standard run which detects environment/params.
    mcp.run()
