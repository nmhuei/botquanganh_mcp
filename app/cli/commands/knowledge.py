from __future__ import annotations

from typing import Any

from app.cli.client import RESTClient
from app.cli.context import CLIContext
from app.cli.output import emit_json, key_values, table


def _query(args, section: str) -> dict[str, Any]:
    return {
        "section": section,
        "query": getattr(args, "query", ""),
        "category": getattr(args, "category", ""),
        "available_only": str(not getattr(args, "include_unavailable", False)).lower(),
        "include_versions": str(getattr(args, "versions", False)).lower(),
        "include_uncatalogued": str(getattr(args, "uncatalogued", False)).lower(),
        "refresh": str(getattr(args, "refresh", False)).lower(),
    }


def _render_guides(guide: dict[str, Any]) -> None:
    documents = guide.get("documents", [])
    for index, document in enumerate(documents):
        if index:
            print()
        print(f"===== {document.get('name', 'guide')} =====")
        content = str(document.get("content", ""))
        print(content, end="" if content.endswith("\n") else "\n")
        if document.get("truncated"):
            print("[truncated]")


def _render_inventory(inventory: dict[str, Any]) -> None:
    summary = inventory.get("summary", {})
    key_values(
        [
            ("Catalogued", summary.get("catalogued", 0)),
            ("Available", summary.get("available", 0)),
            ("Returned", summary.get("returned", 0)),
            ("Categories", ", ".join(summary.get("categories", []))),
        ]
    )
    tools = inventory.get("tools", [])
    if tools:
        print()
        table(
            ["Name", "Available", "Category", "Version", "Purpose"],
            [
                [
                    tool.get("name", ""),
                    "yes" if tool.get("available") else "no",
                    tool.get("category", ""),
                    tool.get("version", "") or "",
                    tool.get("purpose", ""),
                ]
                for tool in tools
            ],
        )
    uncatalogued = inventory.get("uncatalogued_commands", [])
    if uncatalogued:
        print("\nUncatalogued PATH commands:")
        table(["Name", "Path"], [[item.get("name", ""), item.get("path", "")] for item in uncatalogued])


def handle_knowledge(ctx: CLIContext, args) -> int:
    section = args.knowledge_command
    client = RESTClient(ctx.base_url, ctx.token, ctx.request_timeout)
    result = client.get("/api/v1/knowledge", query=_query(args, section))
    if ctx.json_output:
        emit_json(result)
        return 0

    if section == "overview":
        overview = result.get("overview", {})
        key_values(
            [
                ("Profile", overview.get("profile", "")),
                ("Workspace", overview.get("workspace", "")),
                ("Restricted", overview.get("restrict_to_workspace", "")),
                ("Policy", overview.get("command_policy", "")),
                ("Knowledge dir", overview.get("knowledge_dir", "")),
                ("Guide files", ", ".join(overview.get("guide_files", []))),
            ]
        )
        return 0
    if section == "guide":
        _render_guides(result.get("guide", {}))
        return 0
    if section == "tools":
        _render_inventory(result.get("inventory", {}))
        return 0
    if section == "search":
        _render_guides(result.get("guide", {}))
        if result.get("guide", {}).get("documents"):
            print()
        _render_inventory(result.get("inventory", {}))
        return 0
    if section == "all":
        overview = result.get("overview", {})
        key_values(
            [
                ("Profile", overview.get("profile", "")),
                ("Workspace", overview.get("workspace", "")),
                ("Policy", overview.get("command_policy", "")),
            ]
        )
        print()
        _render_guides(result.get("guide", {}))
        print()
        _render_inventory(result.get("inventory", {}))
    return 0
