from __future__ import annotations

from typing import Any

from app.cli.client import RESTClient
from app.cli.context import CLIContext
from app.cli.output import emit_json, emit_quiet, renderer_for
from app.cli.progress import progress_for


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


def _render_guides(ctx: CLIContext, guide: dict[str, Any]) -> None:
    renderer = renderer_for(ctx)
    documents = guide.get("documents", [])
    for index, document in enumerate(documents):
        if index:
            renderer.blank()
        renderer.section(str(document.get("name", "Guide")))
        content = str(document.get("content", ""))
        for line in content.rstrip("\n").splitlines():
            renderer.summary(line)
        if document.get("truncated"):
            renderer.warning("Guide content was truncated.")


def _render_inventory(ctx: CLIContext, inventory: dict[str, Any]) -> None:
    renderer = renderer_for(ctx)
    summary = inventory.get("summary", {})
    renderer.facts(
        [
            ("Catalogued", summary.get("catalogued", 0)),
            ("Available", summary.get("available", 0)),
            ("Returned", summary.get("returned", 0)),
            ("Categories", ", ".join(summary.get("categories", []))),
        ]
    )
    tools = inventory.get("tools", [])
    if tools:
        renderer.blank()
        renderer.table(
            ["NAME", "STATE", "CATEGORY", "VERSION", "PURPOSE"],
            [
                [
                    tool.get("name", ""),
                    "available" if tool.get("available") else "offline",
                    tool.get("category", ""),
                    tool.get("version", "") or "",
                    tool.get("purpose", ""),
                ]
                for tool in tools
            ],
        )
    uncatalogued = inventory.get("uncatalogued_commands", [])
    if uncatalogued:
        renderer.blank()
        renderer.section("Uncatalogued PATH commands")
        renderer.table(
            ["NAME", "PATH"],
            [[item.get("name", ""), item.get("path", "")] for item in uncatalogued],
        )


def _quiet_guides(guide: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for document in guide.get("documents", []):
        content = str(document.get("content", ""))
        lines.extend(content.rstrip("\n").splitlines())
    return lines


def _quiet_inventory(inventory: dict[str, Any]) -> list[str]:
    return [str(tool.get("name", "")) for tool in inventory.get("tools", [])]


def handle_knowledge(ctx: CLIContext, args) -> int:
    section = args.knowledge_command
    client = RESTClient(ctx.base_url, ctx.token, ctx.request_timeout)
    with progress_for(ctx, f"Loading knowledge {section}...") as progress:
        result = client.get("/api/v1/knowledge", query=_query(args, section))
        progress.finish(f"Loaded knowledge {section}")
    if ctx.json_output:
        emit_json(result)
        return 0

    if ctx.quiet:
        if section == "overview":
            overview = result.get("overview", {})
            emit_quiet(
                [
                    f"profile={overview.get('profile', '')}",
                    f"workspace={overview.get('workspace', '')}",
                    f"policy={overview.get('command_policy', '')}",
                    f"knowledge_dir={overview.get('knowledge_dir', '')}",
                ]
            )
        elif section == "guide":
            emit_quiet(_quiet_guides(result.get("guide", {})))
        elif section == "tools":
            emit_quiet(_quiet_inventory(result.get("inventory", {})))
        else:
            emit_quiet(
                [
                    *_quiet_guides(result.get("guide", {})),
                    *_quiet_inventory(result.get("inventory", {})),
                ]
            )
        return 0

    renderer = renderer_for(ctx)
    renderer.header("Host knowledge", section.capitalize())
    renderer.blank()

    if section == "overview":
        overview = result.get("overview", {})
        renderer.status("success", "Knowledge source loaded")
        renderer.blank()
        renderer.facts(
            [
                ("Profile", overview.get("profile", "")),
                ("Workspace", overview.get("workspace", "")),
                (
                    "Restricted",
                    "yes" if overview.get("restrict_to_workspace") else "no",
                ),
                ("Policy", overview.get("command_policy", "")),
                ("Knowledge directory", overview.get("knowledge_dir", "")),
                ("Guide files", ", ".join(overview.get("guide_files", []))),
            ]
        )
        renderer.blank()
        renderer.hint("bqa knowledge tools", "Inspect tools with")
        return 0
    if section == "guide":
        _render_guides(ctx, result.get("guide", {}))
        return 0
    if section == "tools":
        _render_inventory(ctx, result.get("inventory", {}))
        return 0
    if section == "search":
        _render_guides(ctx, result.get("guide", {}))
        if result.get("guide", {}).get("documents"):
            renderer.blank()
        _render_inventory(ctx, result.get("inventory", {}))
        return 0
    if section == "all":
        overview = result.get("overview", {})
        renderer.facts(
            [
                ("Profile", overview.get("profile", "")),
                ("Workspace", overview.get("workspace", "")),
                ("Policy", overview.get("command_policy", "")),
            ]
        )
        renderer.blank()
        _render_guides(ctx, result.get("guide", {}))
        renderer.blank()
        _render_inventory(ctx, result.get("inventory", {}))
    return 0
