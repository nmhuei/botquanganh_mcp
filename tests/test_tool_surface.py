import json
import os
import subprocess
import sys

SUPER_TOOLS = {
    "workspace_explore",
    "workspace_edit",
    "workspace_search",
    "terminal_execute",
    "web_intelligence",
    "server_info",
    "workspace_context",
    "task",
}

EXPECTED_TOOLS = SUPER_TOOLS


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


def test_tool_surface_is_exactly_8_super_tools():
    assert _list_tools() == EXPECTED_TOOLS


def test_server_info_description_covers_discovery():
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
    server = next(tool for tool in tools if tool.name == "server_info")
    print(json.dumps(server.description))

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

    description = json.loads(proc.stdout).lower()
    assert "server discovery" in description or "status" in description



def test_tool_surface_excludes_retired_legacy_operations():
    tools = _list_tools()
    assert len(tools) == 8
    assert not tools.intersection(
        {
            "host_workspace_bind",
            "host_workspace_list",
            "host_save_note",
            "host_session_bind",
            "host_session_list",
            "health_check",
            "host_knowledge",
            "ctf_fetch",
        }
    )
