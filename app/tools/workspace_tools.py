"""Chat workspace MCP tools: per-chat bind and timestamped note log.

app.chat_workspace is optional infrastructure: both tools degrade to a
structured NOT_AVAILABLE payload (or a conventional local path for notes)
instead of raising when the module or the feature flag is absent.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import app.config
from app.chat_errors import (
    tool_success,
    tool_unavailable,
    to_tool_error,
    validate_chat_id,
)
from app.mcp_server import mcp

_NOTE_HINTS = (
    "Append notes with host_save_note; each entry lands in notes/log.txt.",
    "Read files inside this workspace with host_read_file using absolute paths.",
    "Keep chat-specific files under this path so sessions stay isolated.",
)


def _chat_root() -> Path:
    raw = getattr(app.config, "HOST_CHAT_ROOT", None) or str(
        app.config.HOST_WORKSPACE_DIR
    )
    return Path(str(raw)).expanduser().resolve()


def _workspaces_enabled() -> bool:
    # HOST_CHAT_WORKSPACES defaults to false in app.config; absent key = off.
    return bool(getattr(app.config, "HOST_CHAT_WORKSPACES", False))


def _load_workspace_module() -> Any:
    # sys.modules first: once the real module has been imported anywhere, the
    # parent package keeps a stale attribute that a plain import would prefer,
    # hiding test doubles installed in sys.modules.
    module = sys.modules.get("app.chat_workspace")
    if module is not None:
        return module
    # A None entry in sys.modules makes this raise ImportError, which callers
    # use to simulate missing infrastructure.
    import app.chat_workspace as workspace_module

    return workspace_module


def _workspace_path_from(result: Any) -> Path | None:
    if isinstance(result, dict):
        for key in ("path", "workspace", "root", "dir"):
            value = result.get(key)
            if isinstance(value, (str, Path)):
                return Path(str(value))
        return None
    for attr in ("path", "root", "workspace_path", "workspace_dir", "dir"):
        value = getattr(result, attr, None)
        if isinstance(value, (str, Path)):
            return Path(str(value))
    return None


# Enforce-mode exemption marker: host_workspace_bind is the only HOST_TOOLS
# entry listed in app.tools.host.BIND_EXEMPT_TOOLS, because binding IS the
# way in — every other tool requires a bound chat id once enforce is active.
@mcp.tool(
    name="host_workspace_bind",
    description=(
        "Create or re-bind the per-chat host workspace for a chat id and return "
        "its absolute path plus usage hints. Ids are 6-64 characters from "
        "letters, digits, '.', '-' and '_', starting with a letter or digit."
    ),
)
async def host_workspace_bind(chat_id: str) -> dict[str, Any]:
    try:
        validated = validate_chat_id(chat_id)
        if not _workspaces_enabled():
            return tool_unavailable(
                "host_workspace_bind", reason="Chat workspaces are disabled."
            )
        try:
            workspace_module = _load_workspace_module()
        except ImportError:
            return tool_unavailable(
                "host_workspace_bind",
                reason="Chat workspace infrastructure is not installed.",
            )
        manager = workspace_module.WorkspaceManager(_chat_root())
        bound = manager.create_or_bind(validated)
        workspace_dir = _workspace_path_from(bound)
        if workspace_dir is None:
            raise ValueError("create_or_bind returned no workspace path")
        resolved = str(workspace_dir.expanduser().resolve())
        hints = list(_NOTE_HINTS[:3])
        created = getattr(bound, "created", None)
        resumed_hint = getattr(bound, "resumed_hint", None)
        message = f"Workspace ready at {resolved}"
        if resumed_hint:
            message = f"{message} ({resumed_hint})"
        return tool_success(
            message,
            chat_id=validated,
            workspace=resolved,
            created=created,
            hints=hints,
            lines=[resolved, *hints],
        )
    except Exception as exc:
        return to_tool_error(exc)


@mcp.tool(
    name="host_save_note",
    description=(
        "Append '<utc-timestamp> <text>' as one line to the chat workspace notes "
        "log (notes/log.txt). Without chat_id the shared root log is used; "
        "interior line breaks are collapsed so every note stays on its own line."
    ),
)
async def host_save_note(text: str, chat_id: str | None = None) -> dict[str, Any]:
    try:
        cleaned = " ".join(text.split())
        if not cleaned:
            return {
                "ok": False,
                "error": {
                    # Not part of the E-catalog: plain argument validation.
                    "code": "INVALID_ARGUMENT",
                    "name": "EMPTY_NOTE",
                    "message": "Note text is empty.",
                    "suggestion": "Provide non-blank text for the note.",
                },
            }
        # Enforce-mode parity with the other HOST_TOOLS entries: saving a note
        # writes into the workspace, so it is gated too. It never performs the
        # bind itself — the caller must bind first and reuse the same chat_id.
        from app.tools.host import _guard_chat_id

        validated, rejection = _guard_chat_id("host_save_note", chat_id)
        if rejection is not None:
            return rejection
        notes_file = _resolve_notes_file(validated)
        notes_file.parent.mkdir(parents=True, exist_ok=True)
        line = f"{datetime.now(timezone.utc).isoformat()} {cleaned}\n"
        with notes_file.open("a", encoding="utf-8") as handle:
            handle.write(line)
        return tool_success(
            f"Note saved to {notes_file}",
            path=str(notes_file),
            bytes_written=len(line.encode("utf-8")),
        )
    except Exception as exc:
        return to_tool_error(exc)


def _resolve_notes_file(validated: str | None) -> Path:
    root = _chat_root()
    if validated is None:
        return root / "notes" / "log.txt"
    if _workspaces_enabled():
        try:
            workspace_module = _load_workspace_module()
        except ImportError:
            workspace_module = None
        if workspace_module is not None:
            manager = workspace_module.WorkspaceManager(root)
            workspace_dir = _workspace_path_from(manager.create_or_bind(validated))
            if workspace_dir is not None:
                return workspace_dir.expanduser() / "notes" / "log.txt"
    # Graceful degradation: conventional location derived from the validated id.
    return root / validated / "notes" / "log.txt"
