"""Unified workspace exploration tool: hierarchy inspection & windowed file reading.

Consolidates directory tree exploration and chunked file reading into a single
evolved super-tool with binary file guards, depth control, and pagination.
"""

from __future__ import annotations

import mimetypes
import os
import stat
from pathlib import Path
from typing import Any, Optional

import app.config
from app.host.paths import display_host_path, resolve_host_path
from app.mcp_server import mcp
from app.security import format_error_response
from app.tools_common import (
    _begin_workspace_journal,
    _finish_workspace_journal,
    _guard_chat_id,
    _record_tool_call,
    bridge_payload_ceiling,
    enforce_bridge_payload_limit,
)

_DEFAULT_LINE_COUNT = 150
_MAX_LINE_COUNT = 1000
_DEFAULT_MAX_DEPTH = 2
_MAX_EXPLORE_DEPTH = 5
_BINARY_PEEK_SIZE = 8192
_MAX_LINE_LENGTH = 8192
_MAX_READ_PAYLOAD_BYTES = 450_000

_IGNORED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "build",
    "dist",
}


def _is_binary_file(path: Path) -> bool:
    """Safely inspect the leading bytes of a file to detect binary formats."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(_BINARY_PEEK_SIZE)
        if b"\x00" in chunk:
            return True
        chunk.decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True
    except Exception:
        return True


def _file_metadata(path: Path) -> dict[str, Any]:
    mime, _ = mimetypes.guess_type(str(path))
    file_stat = path.stat()
    return {
        "size_bytes": file_stat.st_size,
        "extension": path.suffix.lower(),
        "mime_type": mime or "application/octet-stream",
        "modified_ns": file_stat.st_mtime_ns,
    }


def _explore_directory_tree(
    root: Path,
    depth: int,
    max_depth: int,
    show_hidden: bool,
    entry_budget: dict[str, Any],
) -> list[dict[str, Any]]:
    if depth > max_depth:
        return []

    entries: list[dict[str, Any]] = []
    try:
        dir_items = sorted(
            root.iterdir(),
            key=lambda p: (not p.is_dir(), p.name.lower()),
        )
    except (PermissionError, OSError) as exc:
        return [{"error": str(exc)}]

    for item in dir_items:
        if not show_hidden and item.name in _IGNORED_DIRS:
            continue
        if not show_hidden and item.name.startswith(".") and item.name not in {".", ".."}:
            continue
        if entry_budget["remaining"] <= 0:
            entry_budget["truncated"] = True
            break

        entry_budget["remaining"] -= 1
        item_info: dict[str, Any] = {
            "name": item.name,
            "path": display_host_path(item, resolve=False),
        }

        try:
            item_stat = item.stat()
            is_dir = stat.S_ISDIR(item_stat.st_mode)
            item_info["is_directory"] = is_dir
            item_info["size_bytes"] = 0 if is_dir else item_stat.st_size

            if is_dir:
                if depth < max_depth:
                    item_info["children"] = _explore_directory_tree(
                        item,
                        depth + 1,
                        max_depth,
                        show_hidden,
                        entry_budget,
                    )
            else:
                item_info["is_binary"] = _is_binary_file(item) if item_stat.st_size > 0 else False
        except OSError as exc:
            item_info["error"] = str(exc)

        entries.append(item_info)
        entry_budget["returned"] += 1

    return entries


def _read_windowed_file(
    path: Path,
    start_line: int,
    line_count: int,
) -> dict[str, Any]:
    start = max(1, start_line)
    limit = max(1, min(line_count, _MAX_LINE_COUNT))

    formatted_lines: list[dict[str, Any]] = []
    total_lines = 0
    current_payload_bytes = 0
    truncated = False

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line_idx, line_raw in enumerate(f, start=1):
            total_lines = line_idx
            if start <= line_idx < (start + limit) and not truncated:
                clean_text = line_raw.rstrip("\r\n")
                if len(clean_text) > _MAX_LINE_LENGTH:
                    clean_text = clean_text[:_MAX_LINE_LENGTH] + "...[line truncated]"
                encoded_line_len = len(clean_text.encode("utf-8"))
                if current_payload_bytes + encoded_line_len > _MAX_READ_PAYLOAD_BYTES:
                    truncated = True
                else:
                    current_payload_bytes += encoded_line_len
                    formatted_lines.append(
                        {
                            "line": line_idx,
                            "text": clean_text,
                        }
                    )

    end_line = formatted_lines[-1]["line"] if formatted_lines else (start if total_lines > 0 else 0)
    has_more = (end_line < total_lines) or truncated

    res = {
        "ok": True,
        "mode": "read",
        "path": display_host_path(path),
        "start_line": start if total_lines > 0 else 0,
        "end_line": end_line,
        "total_lines": total_lines,
        "has_more": has_more,
        "lines": formatted_lines,
    }
    if truncated:
        res["truncated"] = True
        res["truncation_reason"] = "Payload ceiling reached under 512KB. Use pagination with start_line to read more."
    return res


@mcp.tool(
    name="workspace_explore",
    description=(
        "Unified workspace exploration super-tool. Inspects directory hierarchies or "
        "reads file content in controlled line windows. Bind workspace_context before use "
        "and pass the bound chat_id. Automatically detects binary files to prevent context "
        "overflow and applies a configured total-entry limit to recursive listings. Returns "
        "truncated=true when the limit cuts a listing. Requires an attributable chat_id "
        "in enforce mode."
    ),
)
def workspace_explore(
    path: str = ".",
    action: Optional[str] = None,
    max_depth: int = _DEFAULT_MAX_DEPTH,
    show_hidden: bool = False,
    start_line: int = 1,
    line_count: int = _DEFAULT_LINE_COUNT,
    chat_id: Optional[str] = None,
) -> dict[str, Any]:
    """Explore directories or inspect files in a windowed, context-safe manner."""
    validated, rejection = _guard_chat_id("workspace_explore", chat_id)
    if rejection is not None:
        return rejection

    journal_details = {
        "path": path,
        "action": action,
        "start_line": start_line,
        "line_count": line_count,
    }
    journal_op = _begin_workspace_journal("workspace_explore", validated, journal_details)

    try:
        resolved = resolve_host_path(path)
        if not resolved.exists():
            result = {
                "ok": False,
                "error": {
                    "code": "PATH_NOT_FOUND",
                    "message": f"Target path does not exist: {path}",
                },
            }
        else:
            resolved_action = action
            if resolved_action is None:
                resolved_action = "list" if resolved.is_dir() else "read"

            if resolved_action in {"list", "tree"}:
                if not resolved.is_dir():
                    result = {
                        "ok": False,
                        "error": {
                            "code": "NOT_A_DIRECTORY",
                            "message": f"Expected a directory for list action: {path}",
                        },
                    }
                else:
                    bounded_depth = max(0, min(max_depth, _MAX_EXPLORE_DEPTH))
                    entry_budget = {
                        "remaining": app.config.MAX_WORKSPACE_EXPLORE_ENTRIES,
                        "returned": 0,
                        "truncated": False,
                    }
                    entries = _explore_directory_tree(
                        resolved,
                        depth=0,
                        max_depth=bounded_depth,
                        show_hidden=show_hidden,
                        entry_budget=entry_budget,
                    )
                    result = {
                        "ok": True,
                        "mode": "directory",
                        "path": display_host_path(resolved),
                        "max_depth": bounded_depth,
                        "total_entries": len(entries),
                        "returned_entries": entry_budget["returned"],
                        "truncated": entry_budget["truncated"],
                        "entries": entries,
                    }
            elif resolved_action == "read":
                if not resolved.is_file():
                    result = {
                        "ok": False,
                        "error": {
                            "code": "NOT_A_FILE",
                            "message": f"Expected a file for read action: {path}",
                        },
                    }
                elif _is_binary_file(resolved):
                    metadata = _file_metadata(resolved)
                    result = {
                        "ok": True,
                        "mode": "binary",
                        "path": display_host_path(resolved),
                        "message": "Binary file detected; text content withheld to protect context buffer.",
                        **metadata,
                    }
                elif line_count > _MAX_LINE_COUNT:
                    oversized = {
                        "requested_line_count": line_count,
                        "max_line_count": _MAX_LINE_COUNT,
                        "overflow": "x" * (bridge_payload_ceiling() + 100),
                    }
                    result = enforce_bridge_payload_limit(oversized, "workspace_explore")
                    result["error"]["message"] = (
                        f"Requested line_count ({line_count}) exceeds maximum allowed "
                        f"window of {_MAX_LINE_COUNT} lines."
                    )
                else:
                    result = _read_windowed_file(resolved, start_line, line_count)
            else:
                result = {
                    "ok": False,
                    "error": {
                        "code": "INVALID_ACTION",
                        "message": f"Unknown explore action: {action}. Expected 'list', 'tree', or 'read'.",
                    },
                }
    except Exception as exc:
        result = format_error_response(exc)

    _record_tool_call("workspace_explore", validated)
    _finish_workspace_journal(
        "workspace_explore",
        validated,
        journal_op,
        ok=isinstance(result, dict) and bool(result.get("ok", False)),
        details=journal_details,
    )
    if isinstance(result, dict):
        result = enforce_bridge_payload_limit(result, "workspace_explore")
    return result
