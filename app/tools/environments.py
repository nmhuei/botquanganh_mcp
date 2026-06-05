from app.mcp_server import mcp
from app.tools.health import get_runner_environments as _get_runner_environments


@mcp.tool(
    name="get_runner_environments",
    description="Retrieve details about advanced Docker runner environments, CTF libraries, and usage details."
)
def get_runner_environments() -> dict:
    return _get_runner_environments()
