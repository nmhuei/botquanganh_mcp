import os
import subprocess
import sys


def test_basic_surface_does_not_load_agent_tools_by_side_effect():
    env = {
        **os.environ,
        "ENABLE_ADVANCED_TOOLS": "false",
        "ENABLE_AGENT_TOOLS": "false",
        "ENABLE_WORKSPACE_TOOLS": "false",
        "DISABLE_SECURITY_POLICIES": "false",
        "ALLOWED_TCP_TARGETS": "",
    }
    code = """
import asyncio
import json
import app.main
from app.mcp_server import mcp

async def main():
    tools = await mcp.list_tools()
    print(json.dumps(sorted(tool.name for tool in tools)))

asyncio.run(main())
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    tool_names = set(__import__("json").loads(proc.stdout))

    assert "ctf_harness_check" in tool_names
    assert "agent_run_command" not in tool_names
    assert "agent_write_file" not in tool_names
