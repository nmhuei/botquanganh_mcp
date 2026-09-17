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


def _rehydrate_session_context(ws_dir: Path) -> dict[str, Any]:
    """Extract recent command history, notes, and workspace files for session resumption."""
    import json

    recent_commands: list[dict[str, Any]] = []
    journal_file = ws_dir / "journal.jsonl"
    if journal_file.is_file():
        try:
            lines = journal_file.read_text(encoding="utf-8", errors="replace").splitlines()
            ops_started: dict[str, dict[str, Any]] = {}
            ops_result: dict[str, dict[str, Any]] = {}
            op_order: list[str] = []

            for line in lines[-120:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    op_id = data.get("op") or f"anon-{len(op_order)}"
                    event_type = data.get("type")
                    if event_type == "op_started":
                        ops_started[op_id] = data
                        if op_id not in op_order:
                            op_order.append(op_id)
                    elif event_type == "op_result" or "ok" in data:
                        ops_result[op_id] = data
                        if op_id not in op_order:
                            op_order.append(op_id)
                except Exception:
                    pass

            for op_id in reversed(op_order):
                started = ops_started.get(op_id, {})
                result = ops_result.get(op_id, {})
                s_payload = started.get("payload", {}) or started.get("details", {}) or {}
                r_payload = result.get("payload", {}) or result.get("details", {}) or {}

                tool = started.get("kind") or result.get("kind") or "cmd"
                cmd = (
                    s_payload.get("intent")
                    or s_payload.get("command")
                    or r_payload.get("command")
                    or s_payload.get("cmd")
                    or r_payload.get("cmd")
                    or ""
                )
                if (not cmd or cmd == "<redacted>") and s_payload.get("path"):
                    cmd = f"{tool} {s_payload['path']}"
                elif not cmd or cmd == "<redacted>":
                    cmd = s_payload.get("intent") or tool

                ok = result.get("ok", True)
                exit_code = r_payload.get("exit_code", 0 if ok else 1)
                stdout = str(r_payload.get("stdout") or r_payload.get("stdout_preview") or "")[:250]
                ts = result.get("ts") or started.get("ts") or ""

                recent_commands.append({
                    "tool": tool,
                    "command": str(cmd)[:150],
                    "exit_code": exit_code,
                    "ok": bool(ok),
                    "stdout_preview": stdout,
                    "timestamp": ts,
                })
                if len(recent_commands) >= 5:
                    break
        except Exception:
            pass

    notes = ""
    notes_file = ws_dir / "notes" / "log.txt"
    if notes_file.is_file():
        try:
            note_lines = [ln.strip() for ln in notes_file.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
            notes = "\n".join(note_lines[-10:])
        except Exception:
            pass
    elif (ws_dir / "STATE.md").is_file():
        try:
            notes = (ws_dir / "STATE.md").read_text(encoding="utf-8", errors="replace")[:600]
        except Exception:
            pass

    files: list[str] = []
    try:
        for entry in sorted(ws_dir.iterdir()):
            if not entry.name.startswith(".") and entry.name not in {"journal.jsonl", "meta.json", "STATE.md", "notes"}:
                files.append(entry.name)
            if len(files) >= 15:
                break
    except Exception:
        pass

    return {
        "recent_commands": recent_commands,
        "recent_notes": notes,
        "workspace_files": files,
    }


# Enforce-mode exemption marker: host_workspace_bind and host_workspace_list are the only
# entries in app.tools.host.BIND_EXEMPT_TOOLS.
@mcp.tool(
    name="host_workspace_bind",
    description=(
        "MANDATORY PRE-FLIGHT STEP: Initialize or resume a host workspace/session. "
        "Call this tool ONCE at the start of work before executing any commands or editing files. "
        "- Calling without arguments automatically creates a brand new workspace/session. "
        "- To start a brand new workspace with a custom label, pass label='<name>'. "
        "- To resume the most recent workspace, pass resume_id='latest' (or session_id='latest'). "
        "- To resume a specific workspace, pass resume_id='<chat_id>' (or session_id='<chat_id>'). "
        "When reconnecting to an existing workspace, previous command history, notes, and files are automatically restored. "
        "Once bound, REUSE the returned chat_id for all subsequent host tool calls."
    ),
)
async def host_workspace_bind(
    label: str | None = None,
    resume_id: str | None = None,
    resume_token: str | None = None,
    new: bool = False,
    chat_id: str | None = None,
    session_id: str | None = None,
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
        target_id = None if new else (resume_id if resume_id is not None else (chat_id if chat_id is not None else session_id))

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
            or (target_id if target_id and target_id not in {"latest", "@latest"} else "")
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

        context_data = _rehydrate_session_context(Path(resolved)) if not created else {
            "recent_commands": [],
            "recent_notes": "",
            "workspace_files": [],
        }

        extra_fields: dict[str, Any] = {
            "chat_id": assigned_id,
            "session_id": assigned_id,
            "workspace": resolved,
            "workspace_dir": resolved,
            "created": bool(created),
            "is_new": bool(created),
            "recent_commands": context_data["recent_commands"],
            "recent_notes": context_data["recent_notes"],
            "workspace_files": context_data["workspace_files"],
            "hints": hints,
            "lines": [resolved, *hints],
            "resume_prompt": resume_prompt_text,
            "resume_badge_markdown": resume_badge_md,
            "instructions": f"Workspace '{assigned_id}' is active. Include chat_id='{assigned_id}' in subsequent tool calls.",
        }
        if session_token:
            extra_fields["session_token"] = session_token
        if auto_hydrated is not None:
            extra_fields["auto_hydrated_context"] = auto_hydrated

        from app.tools.host import _record_workspace_journal

        _record_workspace_journal(
            "host_workspace_bind",
            assigned_id,
            {"created": bool(created), "resumed": not bool(created), "new": bool(new)},
            ok=True,
        )
        try:
            from app.chat_identity import bind_chat
            bind_chat(assigned_id)
        except Exception:
            pass
        return tool_success(
            message,
            **extra_fields,
        )
    except Exception as exc:
        return to_tool_error(exc)


def _workspace_last_mtime(ws_dir: Path) -> float:
    try:
        mtime = ws_dir.stat().st_mtime
        for sub in ("journal.jsonl", "STATE.md", "meta.json", "notes/log.txt", "notes"):
            p = ws_dir / sub
            if p.exists():
                try:
                    mtime = max(mtime, p.stat().st_mtime)
                except OSError:
                    pass
        return mtime
    except OSError:
        return 0.0


@mcp.tool(
    name="host_workspace_list",
    description=(
        "MANDATORY PRE-FLIGHT DISCOVERY: List recent host workspaces/sessions with their chat_id, "
        "label, last active time, operations count, last command, and summary. "
        "Call this tool first to check previous workspaces before deciding whether to resume an existing one or start a new one."
    ),
)
async def host_workspace_list(
    limit: int = 10,
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
                sessions=[],
                suggestion="Call host_workspace_bind(new=True, label='<name>') to create your first workspace.",
            )

        archive_root = root / ".archive"
        candidates: list[tuple[float, Path, bool]] = []
        import json
        from datetime import datetime, timezone

        for entry in root.iterdir():
            if entry.is_dir() and not entry.name.startswith("."):
                mtime = _workspace_last_mtime(entry)
                candidates.append((mtime, entry, False))
        if include_archived and archive_root.is_dir():
            for entry in archive_root.iterdir():
                if entry.is_dir() and not entry.name.startswith("."):
                    mtime = _workspace_last_mtime(entry)
                    candidates.append((mtime, entry, True))

        candidates.sort(key=lambda item: item[0], reverse=True)
        now_ts = datetime.now(timezone.utc).timestamp()

        last_active_id = None
        pointer_file = root / ".last_session"
        if pointer_file.is_file():
            try:
                p_data = json.loads(pointer_file.read_text(encoding="utf-8"))
                candidate = p_data.get("chat_id")
                if isinstance(candidate, str) and (
                    (root / candidate).is_dir() or (archive_root / candidate).is_dir()
                ):
                    last_active_id = candidate
            except Exception:
                pass

        workspaces: list[dict[str, Any]] = []
        for idx, (mtime, entry, archived) in enumerate(candidates):
            chat_id = entry.name

            meta_file = entry / "meta.json"
            created_at = None
            label = None
            if meta_file.is_file():
                try:
                    meta_data = json.loads(meta_file.read_text(encoding="utf-8"))
                    created_at = meta_data.get("created_at")
                    label = meta_data.get("label")
                except Exception:
                    pass

            if query:
                q = query.lower()
                matches_id = q in chat_id.lower()
                matches_label = bool(label and q in label.lower())
                if not matches_id and not matches_label:
                    continue

            diff_sec = max(0, int(now_ts - mtime))
            if diff_sec < 60:
                human_time = "just now"
            elif diff_sec < 3600:
                human_time = f"{diff_sec // 60}m ago"
            elif diff_sec < 86400:
                human_time = f"{diff_sec // 3600}h ago"
            else:
                human_time = f"{diff_sec // 86400}d ago"

            ops_count = 0
            last_cmd = ""
            journal_file = entry / "journal.jsonl"
            if journal_file.is_file():
                try:
                    j_lines = journal_file.read_text(encoding="utf-8", errors="replace").splitlines()
                    started_count = sum(1 for line in j_lines if '"op_started"' in line)
                    ops_count = started_count if started_count > 0 else len(j_lines)
                    for j_line in reversed(j_lines[-40:]):
                        if not j_line.strip():
                            continue
                        rec = json.loads(j_line)
                        payload = rec.get("payload", {}) or rec.get("details", {}) or {}
                        cmd_val = payload.get("intent") or payload.get("command") or payload.get("cmd")
                        if (not cmd_val or cmd_val == "<redacted>") and payload.get("path"):
                            kind = rec.get("kind") or "file"
                            cmd_val = f"{kind} {payload['path']}"
                        if cmd_val and cmd_val != "<redacted>":
                            last_cmd = str(cmd_val)[:100]
                            break
                except Exception:
                    pass

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

            is_latest = (chat_id == last_active_id) or (last_active_id is None and not workspaces)

            item = {
                "chat_id": chat_id,
                "session_id": chat_id,
                "label": label or chat_id.replace("cw-", ""),
                "state": "archived" if archived else "active",
                "last_active_human": human_time,
                "created_at": created_at,
                "notes_count": notes_count,
                "ops_count": ops_count,
                "last_command": last_cmd or None,
                "recent_note": recent_note,
                "is_latest": is_latest,
            }
            workspaces.append(item)

        total_matched = len(workspaces)
        try:
            safe_limit = max(1, min(int(limit), 100)) if limit is not None else 10
        except (ValueError, TypeError):
            safe_limit = 10
        limited_workspaces = workspaces[:safe_limit]

        return tool_success(
            f"Found {total_matched} workspace(s).",
            total_count=total_matched,
            workspaces=limited_workspaces,
            sessions=limited_workspaces,
            suggestion=(
                "To resume an existing workspace: call host_workspace_bind(resume_id='<chat_id>'). "
                "To start a new workspace: call host_workspace_bind(new=True, label='<name>')."
            ),
        )
    except Exception as exc:
        return to_tool_error(exc)


# Backward compatibility aliases for Python callers and tests
host_session_list = host_workspace_list
host_session_bind = host_workspace_bind






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
