from pathlib import Path


def test_agent_guidance_requires_bqa_mcp_for_host_operations():
    guidance = Path(__file__).parents[1] / "AGENTS.md"

    assert "Use the connected BQA MCP instead of container.exec for host operations." in guidance.read_text()


def test_mcp_startup_instructions_include_no_container_exec_guidance():
    from app.mcp_server import mcp

    assert "Use the connected BQA MCP for host operations instead of container.exec." in mcp.instructions
