"""Unified workspace editing tool: atomic file writes, appends, and anchored replaces.

Consolidates file write, append, and search & replace operations into a single
evolved super-tool with atomic replacement semantics and AST syntax validation.
"""

from __future__ import annotations

import ast
import difflib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from app.host.paths import display_host_path, resolve_host_path
from app.mcp_server import mcp
from app.security import format_error_response
from app.tools_common import (
    _begin_workspace_journal,
    _finish_workspace_journal,
    _guard_chat_id,
    _record_tool_call,
    enforce_bridge_payload_limit,
)


def _validate_syntax(path: Path, content: str) -> Optional[dict[str, Any]]:
    """Validate content syntax for known formats before committing to disk."""
    suffix = path.suffix.lower()
    if suffix == ".py":
        try:
            ast.parse(content, filename=str(path))
        except SyntaxError as exc:
            return {
                "ok": False,
                "error": {
                    "code": "SYNTAX_ERROR",
                    "language": "python",
                    "line": exc.lineno,
                    "offset": exc.offset,
                    "message": f"Python SyntaxError: {exc.msg} at line {exc.lineno}",
                },
            }
    elif suffix == ".json":
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            return {
                "ok": False,
                "error": {
                    "code": "SYNTAX_ERROR",
                    "language": "json",
                    "line": exc.lineno,
                    "column": exc.colno,
                    "message": f"JSON DecodeError: {exc.msg} at line {exc.lineno}, col {exc.colno}",
                },
            }
    return None


def _atomic_write_file(target: Path, content: str) -> int:
    """Safely commit content via tempfile + fsync + atomic rename."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_fd, temp_path_str = tempfile.mkstemp(
        prefix=".bqa_edit_",
        dir=str(target.parent),
    )
    temp_path = Path(temp_path_str)
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_path, target)
        return len(content.encode("utf-8"))
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


@mcp.tool(
    name="workspace_edit",
    description=(
        "Unified workspace editing super-tool. Performs atomic writes, safe appends, "
        "and anchor-verified text replacements. Validates syntax (Python/JSON) before committing. "
        "Requires an attributable chat_id in enforce mode."
    ),
)
def workspace_edit(
    path: str,
    action: str,
    content: Optional[str] = None,
    old_text: str = "",
    new_text: str = "",
    expected_count: int = 1,
    validate_syntax: bool = True,
    chat_id: Optional[str] = None,
    intent: Optional[str] = None,
) -> dict[str, Any]:
    """Execute unified mutations on host files with atomic guarantees."""
    validated, rejection = _guard_chat_id("workspace_edit", chat_id)
    if rejection is not None:
        return enforce_bridge_payload_limit(rejection, "workspace_edit")

    journal_details = {
        "path": path,
        "action": action,
        "expected_count": expected_count if action == "replace" else None,
    }
    if intent:
        journal_details["intent"] = str(intent).strip()[:300]
    journal_op = _begin_workspace_journal("workspace_edit", validated, journal_details)

    try:
        resolved = resolve_host_path(path)
        normalized_action = action.strip().lower()
        existing = (
            resolved.read_text(encoding="utf-8", errors="replace")
            if resolved.exists()
            else ""
        )

        if normalized_action in {"write", "overwrite"}:
            if content is None:
                result = {
                    "ok": False,
                    "error": {
                        "code": "MISSING_CONTENT",
                        "message": "Content is required for write actions. Use content='' explicitly to clear a file.",
                    },
                }
                _finish_workspace_journal("workspace_edit", validated, journal_op, ok=False, details=journal_details)
                return enforce_bridge_payload_limit(result, "workspace_edit")
            candidate = content
        elif normalized_action == "append":
            candidate = existing + (content or "")
        elif normalized_action in {"replace", "patch"}:
            if not resolved.exists():
                result = {
                    "ok": False,
                    "error": {
                        "code": "FILE_NOT_FOUND",
                        "message": f"Target file does not exist for replacement: {path}",
                    },
                }
                _finish_workspace_journal("workspace_edit", validated, journal_op, ok=False, details=journal_details)
                return enforce_bridge_payload_limit(result, "workspace_edit")

            actual_count = existing.count(old_text)
            if expected_count != -1 and actual_count != expected_count:
                result = {
                    "ok": False,
                    "error": {
                        "code": "ANCHOR_COUNT_MISMATCH",
                        "expected": expected_count,
                        "found": actual_count,
                        "message": (
                            f"Replacement aborted. Expected {expected_count} occurrence(s) "
                            f"of target text, but found {actual_count}."
                        ),
                    },
                }
                _finish_workspace_journal("workspace_edit", validated, journal_op, ok=False, details=journal_details)
                return enforce_bridge_payload_limit(result, "workspace_edit")

            candidate = existing.replace(old_text, new_text)
        else:
            result = {
                "ok": False,
                "error": {
                    "code": "INVALID_ACTION",
                    "message": f"Unknown edit action: {action}. Expected 'write', 'append', or 'replace'.",
                },
            }
            _finish_workspace_journal("workspace_edit", validated, journal_op, ok=False, details=journal_details)
            return enforce_bridge_payload_limit(result, "workspace_edit")

        if validate_syntax:
            syntax_error = _validate_syntax(resolved, candidate)
            if syntax_error is not None:
                _finish_workspace_journal("workspace_edit", validated, journal_op, ok=False, details=journal_details)
                return enforce_bridge_payload_limit(syntax_error, "workspace_edit")

        bytes_written = _atomic_write_file(resolved, candidate)
        total_lines = len(candidate.splitlines())
        diff = difflib.unified_diff(
            existing.splitlines(True),
            candidate.splitlines(True),
            fromfile=f"a/{resolved.name}",
            tofile=f"b/{resolved.name}",
            n=3,
        )

        result = {
            "ok": True,
            "action": normalized_action,
            "path": display_host_path(resolved),
            "bytes_written": bytes_written,
            "total_lines": total_lines,
            "diff_preview": "".join(list(diff)[:30]),
            "lines_changed": abs(total_lines - len(existing.splitlines())),
        }
    except Exception as exc:
        result = format_error_response(exc)

    _record_tool_call("workspace_edit", validated)
    finish_details = dict(journal_details)
    if isinstance(result, dict) and result.get("ok"):
        finish_details["bytes_written"] = result.get("bytes_written")
        finish_details["lines_changed"] = result.get("lines_changed")
        finish_details["diff_preview"] = result.get("diff_preview", "")
        finish_details["stdout"] = result.get("diff_preview", "")

    _finish_workspace_journal(
        "workspace_edit",
        validated,
        journal_op,
        ok=isinstance(result, dict) and bool(result.get("ok", False)),
        details=finish_details,
    )
    return enforce_bridge_payload_limit(result, "workspace_edit")
