from datetime import datetime
from app.mcp_server import mcp
from app.config import RUNNER_IMAGE_PYTHON
from app.logging_audit import log_audit_event


@mcp.tool(name="health_check", description="Verify the MCP server is reachable and running correctly.")
def health_check() -> dict:
    """Verifies connection health and configured runner capabilities."""
    try:
        log_audit_event("HEALTH_CHECK_PASS", {})
        return {
            "ok": True,
            "service": "fallback-runner-mcp",
            "version": "0.1.0",
            "server_time": datetime.utcnow().isoformat() + "Z",
            "runner_images": [RUNNER_IMAGE_PYTHON]
        }
    except Exception as e:
        log_audit_event("HEALTH_CHECK_FAIL", {"tool": "health_check", "error": str(e)})
        raise e

