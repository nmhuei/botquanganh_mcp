import os
import sys
from app.mcp_server import mcp

# Basic tools: lightweight server connectivity checks for ChatGPT.
import app.tools.health
import app.tools.probe
import app.tools.basic_runner
import app.tools.smoke
import app.tools.ctf_harness
from app.config import (
    MCP_BIND_HOST,
    MCP_PORT,
    ENABLE_ADVANCED_TOOLS,
    ENABLE_AGENT_TOOLS,
    ENABLE_WORKSPACE_TOOLS,
    GATEWAY_TOKEN,
)

# 1.2 Startup check for GATEWAY_TOKEN in non-stdio mode
is_stdio = True
for arg in sys.argv:
    if any(mode in arg for mode in ["sse", "streamable-http", "http"]):
        is_stdio = False

if not is_stdio and not GATEWAY_TOKEN:
    print("Error: GATEWAY_TOKEN is not configured. Non-stdio mode requires a non-empty GATEWAY_TOKEN for security.", file=sys.stderr)
    sys.exit(1)

# Advanced tools: Docker runner/workspace/log features. Enabled after running
# scripts/install_advanced_tools.sh or setting ENABLE_ADVANCED_TOOLS=true.
if ENABLE_ADVANCED_TOOLS:
    import app.tools.autonomous_agent
    import app.tools.environments
    import app.tools.fallback
    import app.tools.github_ops
    import app.tools.runs
    import app.tools.shell
    if ENABLE_WORKSPACE_TOOLS:
        import app.tools.workspace

# Agent tools: Local workspace filesystem and shell tools.
if ENABLE_AGENT_TOOLS:
    import app.tools.agent

from app.logging_audit import log_audit_event

# Log server boot
log_audit_event("SERVER_STARTUP", {
    "host": MCP_BIND_HOST,
    "port": MCP_PORT,
    "pid": os.getpid(),
    "advanced_tools_enabled": ENABLE_ADVANCED_TOOLS,
    "workspace_tools_enabled": ENABLE_WORKSPACE_TOOLS,
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
