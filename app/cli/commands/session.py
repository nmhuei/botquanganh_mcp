"""CLI command handlers for 'bqa session' (listing, binding, and current session)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import config as host_config
from app.cli.chats_view import (
    ARCHIVE_DIR_NAME,
    CHAT_ID_PATTERN,
    META_NAME,
    _inventory,
    _resolve_target_chat_id,
    _workspaces_root,
)
from app.cli.context import CLIContext
from app.cli.errors import CLIError, NotFoundCLIError
from app.cli.output import emit_json, emit_quiet, renderer_for


def _relative_time_str(mtime: float) -> str:
    now_ts = datetime.now(timezone.utc).timestamp()
    diff_sec = max(0, int(now_ts - mtime))
    if diff_sec < 60:
        return "just now"
    if diff_sec < 3600:
        return f"{diff_sec // 60}m ago"
    if diff_sec < 86400:
        return f"{diff_sec // 3600}h ago"
    return f"{diff_sec // 86400}d ago"


def _read_last_session_id(root: Path | None) -> str | None:
    if root is None or not root.is_dir():
        return None
    pointer = root / ".last_session"
    if pointer.is_file():
        try:
            data = json.loads(pointer.read_text(encoding="utf-8"))
            candidate = data.get("chat_id")
            if isinstance(candidate, str) and candidate:
                return candidate
        except Exception:
            pass
    return None


def handle_session_list(ctx: CLIContext, args: Any) -> int:
    root = _workspaces_root()
    if root is None or not root.is_dir():
        if ctx.json_output:
            emit_json({"ok": True, "total": 0, "sessions": []})
        elif ctx.quiet:
            emit_quiet("0")
        else:
            renderer = renderer_for(ctx)
            renderer.header("Session list")
            renderer.summary("No workspace directory found.")
        return 0

    include_archived = bool(getattr(args, "all", False))
    limit = max(1, int(getattr(args, "limit", 15) or 15))
    query = str(getattr(args, "query", "") or "").strip().lower()

    candidates: list[tuple[float, Path, bool]] = []
    for entry in root.iterdir():
        if entry.is_dir() and not entry.name.startswith("."):
            candidates.append((entry.stat().st_mtime, entry, False))
    archive_root = root / ARCHIVE_DIR_NAME
    if include_archived and archive_root.is_dir():
        for entry in archive_root.iterdir():
            if entry.is_dir() and not entry.name.startswith("."):
                candidates.append((entry.stat().st_mtime, entry, True))

    candidates.sort(key=lambda item: item[0], reverse=True)
    active_session_id = _read_last_session_id(root)

    sessions: list[dict[str, Any]] = []
    for mtime, entry, archived in candidates:
        chat_id = entry.name
        if query and query not in chat_id.lower():
            continue

        meta_file = entry / META_NAME
        created_at = None
        label = chat_id.replace("cw-", "")
        if meta_file.is_file():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                created_at = meta.get("created_at")
                if meta.get("label"):
                    label = str(meta["label"])
            except Exception:
                pass

        ops_count = 0
        journal_file = entry / "journal.jsonl"
        if journal_file.is_file():
            try:
                ops_count = len(journal_file.read_text(encoding="utf-8", errors="replace").splitlines())
            except Exception:
                pass

        is_current = (chat_id == active_session_id)
        status = "ACTIVE" if is_current else ("archived" if archived else "idle")

        sessions.append({
            "session_id": chat_id,
            "label": label,
            "ops": ops_count,
            "status": status,
            "is_active": is_current,
            "archived": archived,
            "last_active": _relative_time_str(mtime),
            "created_at": created_at,
            "path": str(entry),
        })

    limited = sessions[:limit]

    if ctx.json_output:
        emit_json({"ok": True, "total": len(sessions), "sessions": limited})
        return 0

    if ctx.quiet:
        for s in limited:
            emit_quiet(s["session_id"])
        return 0

    renderer = renderer_for(ctx)
    renderer.header("Agent & Host Sessions", f"{len(sessions)} session(s) found")
    if not limited:
        renderer.summary("No sessions matched the query.")
        return 0

    for s in limited:
        active_flag = " ● [ACTIVE]" if s["is_active"] else ""
        renderer.facts([
            ("Session ID", f"{s['session_id']}{active_flag}"),
            ("Label", s["label"]),
            ("Operations", f"{s['ops']} ops"),
            ("Last active", s["last_active"]),
            ("Status", s["status"]),
            ("Path", s["path"]),
        ], no_wrap=("Session ID", "Path"))
        renderer.blank()

    renderer.hint("bqa session bind <session_id>", "Bind and resume a session with")
    return 0


def handle_session_bind(ctx: CLIContext, args: Any) -> int:
    root = _workspaces_root()
    raw_id = getattr(args, "session_id", None)
    chat_id = _resolve_target_chat_id(root, raw_id)
    assert root is not None

    active_dir = root / chat_id
    archived_dir = root / ARCHIVE_DIR_NAME / chat_id

    # Auto un-archive if archived
    if not active_dir.is_dir() and archived_dir.is_dir():
        try:
            archived_dir.rename(active_dir)
        except OSError as exc:
            raise CLIError(f"Could not unarchive workspace '{chat_id}': {exc}") from exc

    target_dir = active_dir
    if not target_dir.is_dir():
        raise NotFoundCLIError(f"Session workspace '{chat_id}' not found under {root}.", 1)

    # Update .last_session pointer
    pointer_file = root / ".last_session"
    pointer_data = {"chat_id": chat_id, "updated_at": datetime.now(timezone.utc).isoformat()}
    try:
        pointer_file.write_text(json.dumps(pointer_data) + "\n", encoding="utf-8")
    except Exception as exc:
        raise CLIError(f"Could not update .last_session: {exc}") from exc

    prompt = f"Tiếp tục làm việc trong workspace {chat_id}"

    # Extract recent commands from journal
    recent_cmds: list[str] = []
    journal_file = target_dir / "journal.jsonl"
    if journal_file.is_file():
        try:
            for line in reversed(journal_file.read_text(encoding="utf-8", errors="replace").splitlines()[-30:]):
                if not line.strip():
                    continue
                rec = json.loads(line)
                det = rec.get("details", {}) or {}
                cmd = det.get("command") or det.get("cmd")
                if cmd:
                    recent_cmds.append(str(cmd))
                if len(recent_cmds) >= 3:
                    break
        except Exception:
            pass

    payload = {
        "ok": True,
        "chat_id": chat_id,
        "session_id": chat_id,
        "status": "active",
        "path": str(target_dir),
        "resume_prompt": prompt,
        "recent_commands": recent_cmds,
    }

    if ctx.json_output:
        emit_json(payload)
        return 0

    if ctx.quiet:
        emit_quiet(chat_id)
        return 0

    renderer = renderer_for(ctx)
    renderer.header("Session Bind Successful", chat_id)
    renderer.facts([
        ("Session ID", chat_id),
        ("Status", "● ACTIVE (Bound)"),
        ("Workspace", str(target_dir)),
    ], no_wrap=("Session ID", "Workspace"))
    renderer.blank()

    if recent_cmds:
        renderer.summary("Recent operations in this session:")
        for cmd in recent_cmds:
            print(f"  • {cmd}")
        renderer.blank()

    renderer.summary("Resume prompt for LLM / ChatGPT:")
    print(f"  {prompt}\n")
    renderer.hint(f"bqa cmd run --cwd '{target_dir}' <command>", "Run command in this session")
    return 0


def handle_session_current(ctx: CLIContext, _args: Any) -> int:
    root = _workspaces_root()
    active_id = _read_last_session_id(root)
    if not active_id:
        if ctx.json_output:
            emit_json({"ok": False, "active_session": None, "message": "No active session bound."})
        elif ctx.quiet:
            emit_quiet("")
        else:
            renderer = renderer_for(ctx)
            renderer.header("Current Session")
            renderer.summary("No active session bound.")
            renderer.hint("bqa session bind <session_id>", "Bind to a session with")
        return 1

    target_dir = str(root / active_id) if root else ""
    payload = {
        "ok": True,
        "chat_id": active_id,
        "session_id": active_id,
        "path": target_dir,
    }
    if ctx.json_output:
        emit_json(payload)
        return 0

    if ctx.quiet:
        emit_quiet(active_id)
        return 0

    renderer = renderer_for(ctx)
    renderer.header("Current Active Session", active_id)
    renderer.facts([
        ("Session ID", active_id),
        ("Status", "● ACTIVE"),
        ("Path", target_dir),
    ], no_wrap=("Session ID", "Path"))
    return 0


def handle_session_new(ctx: CLIContext, args: Any) -> int:
    root = _workspaces_root()
    if root is None:
        raise CLIError("Chat workspaces root directory is not configured.")
    root.mkdir(parents=True, exist_ok=True)

    label = getattr(args, "label", None)
    from app.chat_workspace import WorkspaceManager

    manager = WorkspaceManager(root)
    bound = manager.create_or_bind(None, label=label)
    chat_id = bound.chat_id
    target_dir = bound.path

    prompt = f"Tiếp tục làm việc trong workspace {chat_id}"
    payload = {
        "ok": True,
        "chat_id": chat_id,
        "session_id": chat_id,
        "is_new": True,
        "status": "active",
        "path": str(target_dir),
        "resume_prompt": prompt,
    }
    if ctx.json_output:
        emit_json(payload)
        return 0
    if ctx.quiet:
        emit_quiet(chat_id)
        return 0

    renderer = renderer_for(ctx)
    renderer.header("New Session Created & Bound", chat_id)
    renderer.facts([
        ("Session ID", chat_id),
        ("Status", "● ACTIVE (New)"),
        ("Workspace", str(target_dir)),
    ], no_wrap=("Session ID", "Workspace"))
    renderer.blank()
    renderer.summary("Resume prompt for LLM / ChatGPT:")
    print(f"  {prompt}\n")
    renderer.hint(f"bqa cmd run --cwd '{target_dir}' <command>", "Run command in this session")
    return 0


def handle_session(ctx: CLIContext, args: Any) -> int:
    action = getattr(args, "session_command", "list") or "list"
    if action in {"new", "create"}:
        return handle_session_new(ctx, args)
    if action in {"list", "ls"}:
        return handle_session_list(ctx, args)
    if action in {"bind", "resume"}:
        return handle_session_bind(ctx, args)
    if action in {"current", "whoami"}:
        return handle_session_current(ctx, args)
    raise CLIError(f"Unknown session subcommand: '{action}'. Use 'new', 'list', 'bind', or 'current'.")

