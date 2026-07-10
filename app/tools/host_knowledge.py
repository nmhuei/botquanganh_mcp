from __future__ import annotations

from typing import Any

import app.config
from app.host.inventory import get_tool_inventory, list_guide_files, read_guides
from app.host.paths import host_workspace_dir
from app.mcp_server import mcp
from app.security import format_error_response


_VALID_SECTIONS = {"overview", "guide", "tools", "search", "all"}


@mcp.tool(
    name="host_knowledge",
    description=(
        "Read the local working guides and inspect tools installed on the user's host. "
        "Use section='overview', 'guide', 'tools', 'search', or 'all'. Tool availability "
        "is detected from the host PATH; optional version probes only execute trusted "
        "version commands declared in TOOL_CATALOG.json."
    ),
)
def host_knowledge(
    section: str = "overview",
    query: str = "",
    category: str = "",
    available_only: bool = True,
    include_versions: bool = False,
    include_uncatalogued: bool = False,
    refresh: bool = False,
) -> dict[str, Any]:
    try:
        normalized_section = section.strip().lower()
        if normalized_section not in _VALID_SECTIONS:
            raise ValueError(
                f"section must be one of: {', '.join(sorted(_VALID_SECTIONS))}"
            )

        guide_names = [path.name for path in list_guide_files()]
        overview = {
            "profile": "host",
            "workspace": str(host_workspace_dir()),
            "restrict_to_workspace": app.config.HOST_RESTRICT_TO_WORKSPACE,
            "command_policy": app.config.HOST_COMMAND_POLICY,
            "inherit_host_environment": app.config.HOST_INHERIT_ENV,
            "knowledge_dir": str(app.config.HOST_KNOWLEDGE_DIR),
            "guide_files": guide_names,
            "sections": sorted(_VALID_SECTIONS),
            "recommended_sequence": [
                "host_knowledge(section='overview')",
                "host_knowledge(section='guide')",
                "host_knowledge(section='tools', query='<needed tool>')",
                "host_check_command(command='<command>')",
                "host_run_command(command='<command>', cwd='<project>')",
            ],
        }

        if normalized_section == "overview":
            inventory = get_tool_inventory(available_only=True)
            return {
                "ok": True,
                "section": "overview",
                "overview": overview,
                "tool_summary": inventory["summary"],
            }

        if normalized_section == "guide":
            return {
                "ok": True,
                "section": "guide",
                "query": query,
                "guide": read_guides(query=query),
            }

        if normalized_section == "tools":
            return {
                "ok": True,
                "section": "tools",
                "query": query,
                "category": category,
                "inventory": get_tool_inventory(
                    available_only=available_only,
                    category=category,
                    query=query,
                    include_versions=include_versions,
                    include_uncatalogued=include_uncatalogued,
                    refresh=refresh,
                ),
            }

        if normalized_section == "search":
            if not query.strip():
                raise ValueError("query is required for section='search'")
            return {
                "ok": True,
                "section": "search",
                "query": query,
                "guide": read_guides(query=query),
                "inventory": get_tool_inventory(
                    available_only=available_only,
                    category=category,
                    query=query,
                    include_versions=include_versions,
                    include_uncatalogued=False,
                    refresh=refresh,
                ),
            }

        return {
            "ok": True,
            "section": "all",
            "overview": overview,
            "guide": read_guides(query=query),
            "inventory": get_tool_inventory(
                available_only=available_only,
                category=category,
                query=query,
                include_versions=include_versions,
                include_uncatalogued=include_uncatalogued,
                refresh=refresh,
            ),
        }
    except Exception as exc:
        return format_error_response(exc)
