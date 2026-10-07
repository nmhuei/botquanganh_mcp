import asyncio

import app.main  # noqa: F401 - registers the MCP tool surface before discovery
from app.mcp_server import mcp


async def _mcp_surface():
    tools = await mcp.list_tools()
    return {
        "server": (mcp.instructions or "").lower(),
        "tools": {tool.name: (tool.description or "").lower() for tool in tools},
    }


def test_mcp_guidance_follows_asd_ste100_and_requires_chat_id():
    surface = asyncio.run(_mcp_surface())
    instructions = surface["server"]
    descriptions = " ".join(surface["tools"].values())

    # ASD-STE100: concise instructions, sentences under 20 words
    words = instructions.split()
    assert len(words) <= 35, f"Instructions too verbose ({len(words)} words): {instructions}"
    for sentence in instructions.split("."):
        clean_sentence = sentence.strip()
        if clean_sentence:
            assert len(clean_sentence.split()) <= 20, f"Sentence exceeds 20 words: {clean_sentence}"

    # Essential invariants
    assert "chat_id" in instructions
    assert "container.exec" in instructions
    assert "tunnel" in instructions

    # Redundant fluff must be omitted (tools self-describe)
    assert "directly inspect files" not in instructions
    assert "solve tasks autonomously" not in instructions
    assert "for basic mcp status" not in instructions

    # Tools self-describe via their schema descriptions
    assert "workspace_context" in descriptions
    assert "chat_id" in descriptions
    for tool_name in ("workspace_explore", "workspace_search"):
        assert "chat_id" in surface["tools"][tool_name]
