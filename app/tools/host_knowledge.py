from __future__ import annotations

from typing import Any, Optional

import app.config
from app.host.inventory import get_tool_inventory, list_guide_files, read_guides
from app.host.paths import host_workspace_dir
from app.mcp_server import mcp
from app.security import format_error_response


_VALID_SECTIONS = {"overview", "guide", "tools", "search", "all"}


def _knowledge_payload(
    section: str,
    query: str,
    category: str,
    available_only: bool,
    include_versions: bool,
    include_uncatalogued: bool,
    refresh: bool,
) -> dict[str, Any]:
    normalized_section = section.strip().lower()
    if normalized_section not in _VALID_SECTIONS:
        raise ValueError(f"section must be one of: {', '.join(sorted(_VALID_SECTIONS))}")

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
    chat_id: Optional[str] = None,
) -> dict[str, Any]:
    # Read-only tool: in off/tag/strict a missing id has nothing to validate,
    # so the legacy fast path stays byte-identical there. Under enforce the
    # shared guard runs even with no id, so unbound callers get E6 before any
    # inventory or guide work happens (reads are gated too).
    if chat_id is None:
        from app.tools.host import _is_enforcing_mode

        if not _is_enforcing_mode():
            try:
                return _knowledge_payload(
                    section,
                    query,
                    category,
                    available_only,
                    include_versions,
                    include_uncatalogued,
                    refresh,
                )
            except Exception as exc:
                return format_error_response(exc)
    from app.tools.host import (
        _guard_chat_id,
        _record_tool_call,
        _record_workspace_journal,
    )

    validated, rejection = _guard_chat_id("host_knowledge", chat_id)
    if rejection is not None:
        return rejection
    try:
        result = _knowledge_payload(
            section,
            query,
            category,
            available_only,
            include_versions,
            include_uncatalogued,
            refresh,
        )
    except Exception as exc:
        result = format_error_response(exc)
    _record_tool_call("host_knowledge", validated)
    _record_workspace_journal(
        "host_knowledge",
        validated,
        {"section": section, "query": query},
        ok=isinstance(result, dict) and bool(result.get("ok", False)),
    )
    return result
