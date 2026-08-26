import asyncio

import app.main  # noqa: F401
from app.mcp_server import mcp
from app.ui.ctf_fetch_result import CTF_FETCH_RESULT_WIDGET_URI


def test_ctf_fetch_widget_resource_is_registered_with_mcp_app_mime_type():
    async def check() -> None:
        resources = await mcp.list_resources()
        resource = next(item for item in resources if str(item.uri) == CTF_FETCH_RESULT_WIDGET_URI)
        assert resource.mime_type == "text/html;profile=mcp-app"

        rendered = await mcp.read_resource(CTF_FETCH_RESULT_WIDGET_URI)
        content = rendered.contents[0]
        assert content.mime_type == "text/html;profile=mcp-app"
        assert "ui/notifications/tool-result" in content.content
        assert "innerHTML" not in content.content
        assert "textContent" in content.content

    asyncio.run(check())


def test_ctf_render_tool_points_to_the_widget_resource():
    async def check() -> None:
        tools = await mcp.list_tools()
        tool = next(item for item in tools if item.name == "ctf_render_fetch_result")
        assert tool.meta["ui"]["resourceUri"] == CTF_FETCH_RESULT_WIDGET_URI
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.openWorldHint is False

    asyncio.run(check())
