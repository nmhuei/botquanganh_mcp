import json
import os
import subprocess
import sys

EXPECTED_TOOLS = {
    "health_check",
    "get_capabilities",
    "host_list_directory",
    "host_read_file",
    "host_write_file",
    "host_replace_in_file",
    "host_append_file",
    "host_make_directory",
    "host_search_text",
    "host_check_command",
    "host_run_command",
    "ctf_fetch_url",
    "ctf_render_fetch_result",
    "ctf_triage_artifact",
    "host_knowledge",
    "host_workspace_bind",
    "host_save_note",
}


def _list_tools() -> set[str]:
    env = {
        **os.environ,
        "REQUIRE_AUTH": "false",
        "HOST_WORKSPACE_DIR": os.getcwd(),
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
        timeout=20,
        check=True,
    )
    return set(json.loads(proc.stdout))


def test_tool_surface_is_exactly_host_core():
    assert _list_tools() == EXPECTED_TOOLS
