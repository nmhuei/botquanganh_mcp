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
    to_tool_error,
    tool_success,
    tool_unavailable,
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
        "Initialize or resume a host workspace. Call this tool ONCE at the start of a session. "
        "By default, calling without arguments automatically resumes the most recent active workspace. "
        "To resume a specific workspace by label or ID, pass resume_id='<label_or_id>'. "
        "To start a brand new workspace, pass new=True and an optional label. "
        "Once bound, REUSE the returned chat_id for all subsequent host tool calls in this conversation."
    ),
)
async def host_workspace_bind(
    label: str | None = None,
    resume_id: str | None = None,
    resume_token: str | None = None,
    new: bool = False,
    chat_id: str | None = None,
) -> dict[str, Any]:
    try:
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
        target_id = resume_id if resume_id is not None else chat_id
        if target_id is None and not new and label is None:
            target_id = "latest"

        if target_id is not None and target_id not in {"latest", "@latest"} and not target_id.startswith("latest:"):
            validate_chat_id(target_id)
        bound = manager.create_or_bind(
            target_id,
            label=label,
            resume_token=resume_token,
            require_token=bool(target_id and target_id not in {"latest", "@latest"}),
        )
        workspace_dir = _workspace_path_from(bound)
        if workspace_dir is None:
            raise ValueError("create_or_bind returned no workspace path")
        resolved = str(workspace_dir.expanduser().resolve())
        hints = list(_NOTE_HINTS[:3])
        created = getattr(bound, "created", None) if not isinstance(bound, dict) else bound.get("created")
        resumed_hint = getattr(bound, "resumed_hint", None) if not isinstance(bound, dict) else bound.get("resumed_hint")
        assigned_id = (
            getattr(bound, "chat_id", "")
            or (bound.get("chat_id") if isinstance(bound, dict) else "")
            or (target_id if target_id not in {"latest", "@latest"} else "")
            or ""
        )
        session_token = getattr(bound, "session_token", None) if not isinstance(bound, dict) else bound.get("session_token")
        auto_hydrated = getattr(bound, "auto_hydrated_context", None) if not isinstance(bound, dict) else bound.get("auto_hydrated_context")

        message = f"Workspace ready at {resolved}"
        if resumed_hint:
            message = f"{message} ({resumed_hint})"

        resume_prompt_text = f"Tiếp tục làm việc trong workspace {assigned_id}" + (f" với token {session_token}" if session_token else "")
        resume_badge_md = (
            f"> 📦 **Workspace Active**: `{assigned_id}`\n"
            f"> 📋 **Prompt phục hồi khi session chết**:\n"
            f"> ```text\n> {resume_prompt_text}\n> ```"
        )

        extra_fields: dict[str, Any] = {
            "chat_id": assigned_id,
            "workspace": resolved,
            "created": created,
            "hints": hints,
            "lines": [resolved, *hints],
            "resume_prompt": resume_prompt_text,
            "resume_badge_markdown": resume_badge_md,
        }
        if session_token:
            extra_fields["session_token"] = session_token
        if auto_hydrated is not None:
            extra_fields["auto_hydrated_context"] = auto_hydrated

        # Binding cannot be journaled before authorization/creation without
        # risking writes to an unowned workspace. Record a compact lifecycle
        # event only after a successful bind, never including the session token.
        from app.tools.host import _record_workspace_journal

        _record_workspace_journal(
            "host_workspace_bind",
            assigned_id,
            {"created": bool(created), "resumed": not bool(created)},
            ok=True,
        )
        return tool_success(
            message,
            **extra_fields,
        )
    except Exception as exc:
        return to_tool_error(exc)


@mcp.tool(
    name="host_workspace_list",
    description=(
        "List recent host workspaces with their chat_id, label, last active time, "
        "and summary. Use this tool when the user wants to resume an earlier project, "
        "continue previous work, or find existing workspaces."
    ),
)
async def host_workspace_list(
    limit: int = 5,
    include_archived: bool = True,
    query: str | None = None,
) -> dict[str, Any]:
    try:
        if not _workspaces_enabled():
            return tool_unavailable(
                "host_workspace_list", reason="Chat workspaces are disabled."
            )
        root = _chat_root()
        if not root.is_dir():
            return tool_success(
                "No workspaces found.",
                total_count=0,
                workspaces=[],
                suggestion="Call host_workspace_bind() to create your first workspace.",
            )

        candidates: list[tuple[float, Path, bool]] = []
        import json
        from datetime import datetime, timezone

        for entry in root.iterdir():
            if entry.is_dir() and not entry.name.startswith("."):
                mtime = entry.stat().st_mtime
                candidates.append((mtime, entry, False))
        archive_root = root / ".archive"
        if include_archived and archive_root.is_dir():
            for entry in archive_root.iterdir():
                if entry.is_dir() and not entry.name.startswith("."):
                    mtime = entry.stat().st_mtime
                    candidates.append((mtime, entry, True))

        candidates.sort(key=lambda item: item[0], reverse=True)
        now_ts = datetime.now(timezone.utc).timestamp()

        workspaces: list[dict[str, Any]] = []
        for mtime, entry, archived in candidates:
            chat_id = entry.name
            if query and query.lower() not in chat_id.lower():
                continue

            meta_file = entry / "meta.json"
            created_at = None
            if meta_file.is_file():
                try:
                    meta_data = json.loads(meta_file.read_text(encoding="utf-8"))
                    created_at = meta_data.get("created_at")
                except Exception:
                    pass

            diff_sec = max(0, int(now_ts - mtime))
            if diff_sec < 60:
                human_time = "just now"
            elif diff_sec < 3600:
                human_time = f"{diff_sec // 60}m ago"
            elif diff_sec < 86400:
                human_time = f"{diff_sec // 3600}h ago"
            else:
                human_time = f"{diff_sec // 86400}d ago"

            notes_file = entry / "notes" / "log.txt"
            notes_count = 0
            recent_note = None
            if notes_file.is_file():
                try:
                    lines = [ln.strip() for ln in notes_file.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
                    notes_count = len(lines)
                    if lines:
                        recent_note = lines[-1]
                except Exception:
                    pass

            item = {
                "chat_id": chat_id,
                "state": "archived" if archived else "active",
                "last_active_human": human_time,
                "created_at": created_at,
                "notes_count": notes_count,
            }
            if recent_note:
                item["recent_note"] = recent_note
            workspaces.append(item)

        total_matched = len(workspaces)
        limited_workspaces = workspaces[:limit]

        return tool_success(
            f"Found {total_matched} workspace(s).",
            total_count=total_matched,
            workspaces=limited_workspaces,
            suggestion="Call host_workspace_bind(resume_id='<chat_id>') to resume any workspace.",
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
    journal_op: str | None = None
    validated: str | None = None
    journal_details: dict[str, Any] = {}
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
        from app.tools.host import (
            _begin_workspace_journal,
            _finish_workspace_journal,
            _guard_chat_id,
        )

        validated, rejection = _guard_chat_id("host_save_note", chat_id)
        if rejection is not None:
            return rejection
        notes_file = _resolve_notes_file(validated)
        line = f"{datetime.now(timezone.utc).isoformat()} {cleaned}\n"
        journal_details = {
            "path": str(notes_file),
            "bytes_written": len(line.encode("utf-8")),
        }
        journal_op = _begin_workspace_journal(
            "host_save_note", validated, journal_details
        )
        notes_file.parent.mkdir(parents=True, exist_ok=True)
        with notes_file.open("a", encoding="utf-8") as handle:
            handle.write(line)
        _finish_workspace_journal(
            "host_save_note",
            validated,
            journal_op,
            ok=True,
            details=journal_details,
        )
        return tool_success(
            f"Note saved to {notes_file}",
            path=str(notes_file),
            bytes_written=journal_details["bytes_written"],
        )
    except Exception as exc:
        if journal_op and validated:
            from app.tools.host import _finish_workspace_journal

            _finish_workspace_journal(
                "host_save_note",
                validated,
                journal_op,
                ok=False,
                details={"error_type": type(exc).__name__},
            )
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
