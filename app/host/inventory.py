from __future__ import annotations

import json
import os
import shutil
import subprocess  # nosec B404
import threading
import time
from pathlib import Path
from typing import Any, Iterable

import app.config


_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {"created_at": 0.0, "catalog": []}


def _catalog_path() -> Path:
    return app.config.HOST_KNOWLEDGE_DIR / "TOOL_CATALOG.json"


def load_tool_catalog() -> list[dict[str, Any]]:
    path = _catalog_path().resolve()
    knowledge_dir = app.config.HOST_KNOWLEDGE_DIR.resolve()
    try:
        path.relative_to(knowledge_dir)
    except ValueError as exc:
        raise PermissionError("Tool catalog path escaped HOST_KNOWLEDGE_DIR") from exc
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("TOOL_CATALOG.json must contain a JSON array")
    return [item for item in data if isinstance(item, dict) and item.get("name")]


def _probe_version(path: str, args: Iterable[str]) -> str | None:
    try:
        result = subprocess.run(  # nosec B603
            [path, *list(args)],
            capture_output=True,
            text=True,
            timeout=2,
            env=dict(os.environ),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (result.stdout or result.stderr).strip()
    if not output:
        return None
    return output.splitlines()[0][:300]


def _build_curated_inventory(include_versions: bool) -> list[dict[str, Any]]:
    catalog = load_tool_catalog()
    inventory: list[dict[str, Any]] = []
    for item in catalog:
        name = str(item["name"])
        path = shutil.which(name)
        record = {
            "name": name,
            "category": item.get("category", "other"),
            "purpose": item.get("purpose", ""),
            "usage_notes": item.get("usage_notes", []),
            "available": bool(path),
            "path": path,
        }
        if include_versions and path:
            args = item.get("version_args", ["--version"])
            if isinstance(args, list) and all(isinstance(arg, str) for arg in args):
                record["version"] = _probe_version(path, args)
        inventory.append(record)
    return inventory


def curated_tool_inventory(
    *,
    include_versions: bool = False,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    cache_key = "with_versions" if include_versions else "without_versions"
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        age = now - float(_CACHE.get("created_at", 0.0))
        if not refresh and cached is not None and age < app.config.HOST_TOOL_CACHE_SECONDS:
            return [dict(item) for item in cached]

    inventory = _build_curated_inventory(include_versions)
    with _CACHE_LOCK:
        _CACHE[cache_key] = [dict(item) for item in inventory]
        _CACHE["created_at"] = now
    return inventory


def discover_path_commands(max_commands: int = 1000) -> list[dict[str, str]]:
    """List executable names visible through PATH without executing them."""
    max_commands = max(1, min(int(max_commands), 5000))
    discovered: dict[str, str] = {}
    for raw_directory in os.environ.get("PATH", "").split(os.pathsep):
        if not raw_directory:
            continue
        directory = Path(raw_directory).expanduser()
        if not directory.is_dir():
            continue
        try:
            entries = directory.iterdir()
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.name in discovered or not entry.is_file():
                    continue
                if os.access(entry, os.X_OK):
                    discovered[entry.name] = str(entry.resolve())
            except OSError:
                continue
            if len(discovered) >= max_commands:
                break
        if len(discovered) >= max_commands:
            break
    return [
        {"name": name, "path": discovered[name]}
        for name in sorted(discovered, key=str.lower)
    ]


def get_tool_inventory(
    *,
    available_only: bool = True,
    category: str = "",
    query: str = "",
    include_versions: bool = False,
    include_uncatalogued: bool = False,
    refresh: bool = False,
) -> dict[str, Any]:
    tools = curated_tool_inventory(
        include_versions=include_versions,
        refresh=refresh,
    )
    normalized_category = category.strip().lower()
    normalized_query = query.strip().lower()

    filtered: list[dict[str, Any]] = []
    for tool in tools:
        if available_only and not tool["available"]:
            continue
        if normalized_category and str(tool.get("category", "")).lower() != normalized_category:
            continue
        searchable = " ".join(
            [
                str(tool.get("name", "")),
                str(tool.get("category", "")),
                str(tool.get("purpose", "")),
                " ".join(str(note) for note in tool.get("usage_notes", [])),
            ]
        ).lower()
        if normalized_query and normalized_query not in searchable:
            continue
        filtered.append(tool)

    available_count = sum(1 for tool in tools if tool["available"])
    categories = sorted(
        {str(tool.get("category", "other")) for tool in tools}, key=str.lower
    )
    response: dict[str, Any] = {
        "catalog_path": str(_catalog_path()),
        "summary": {
            "catalogued": len(tools),
            "available": available_count,
            "returned": len(filtered),
            "categories": categories,
        },
        "tools": filtered,
    }

    if include_uncatalogued:
        catalogued_names = {str(tool["name"]) for tool in tools}
        discovered = discover_path_commands()
        response["uncatalogued_commands"] = [
            item for item in discovered if item["name"] not in catalogued_names
        ]
        response["summary"]["path_commands"] = len(discovered)
        response["summary"]["uncatalogued"] = len(
            response["uncatalogued_commands"]
        )
    return response


def list_guide_files() -> list[Path]:
    root = app.config.HOST_KNOWLEDGE_DIR.resolve()
    if not root.exists():
        return []
    guides: list[Path] = []
    for path in sorted(root.glob("*.md"), key=lambda p: p.name.lower()):
        try:
            resolved = path.resolve()
            resolved.relative_to(root)
        except (OSError, ValueError):
            continue
        if resolved.is_file() and resolved.stat().st_size <= app.config.MAX_SINGLE_FILE_BYTES:
            guides.append(resolved)
    return guides


def read_guides(query: str = "") -> dict[str, Any]:
    normalized_query = query.strip().lower()
    documents: list[dict[str, Any]] = []
    total_bytes = 0
    max_total = min(app.config.MAX_OUTPUT_BYTES, 500_000)
    for path in list_guide_files():
        content = path.read_text(encoding="utf-8", errors="replace")
        if normalized_query and normalized_query not in (
            path.name + "\n" + content
        ).lower():
            continue
        encoded = content.encode("utf-8")
        if total_bytes + len(encoded) > max_total:
            remaining = max(0, max_total - total_bytes)
            content = encoded[:remaining].decode("utf-8", errors="replace")
            documents.append(
                {"name": path.name, "content": content, "truncated": True}
            )
            total_bytes = max_total
            break
        documents.append({"name": path.name, "content": content, "truncated": False})
        total_bytes += len(encoded)
    return {
        "knowledge_dir": str(app.config.HOST_KNOWLEDGE_DIR),
        "documents": documents,
        "document_count": len(documents),
        "total_bytes": total_bytes,
    }
