import atexit
import os
import sys

from app.config import GATEWAY_TOKEN, MCP_BIND_HOST, MCP_PORT, REQUIRE_AUTH
from app.logging_audit import log_audit_event
from app.mcp_server import mcp

# Tool registration is intentionally explicit and host-only.
import app.tools.ctf_http  # noqa: E402,F401
import app.tools.health  # noqa: E402,F401
import app.tools.host  # noqa: E402,F401
import app.tools.host_knowledge  # noqa: E402,F401


@atexit.register
def _shutdown_log() -> None:
    try:
        log_audit_event("SERVER_SHUTDOWN", {"pid": os.getpid()})
    except Exception:  # nosec B110
        pass


is_stdio = not any(
    any(mode in argument for mode in ("sse", "streamable-http", "http"))
    for argument in sys.argv
)
if REQUIRE_AUTH and not is_stdio and not GATEWAY_TOKEN:
    print(
        "Error: GATEWAY_TOKEN is required for HTTP transports when REQUIRE_AUTH=true.",
        file=sys.stderr,
    )
    sys.exit(1)

log_audit_event(
    "SERVER_STARTUP",
    {
        "host": MCP_BIND_HOST,
        "port": MCP_PORT,
        "pid": os.getpid(),
        "tool_profile": "host",
    },
)

if __name__ == "__main__":
    mcp.run()
