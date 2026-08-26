from __future__ import annotations

import json
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import config as host_config
from app.cli.context import CLIContext
from app.cli.errors import CLIError, EXIT_USAGE, NotFoundCLIError
from app.cli.output import emit_json, emit_quiet, external_text, renderer_for

# Verbatim chat-id contract, kept local so this read-only view never imports
# the workspace modules their owners are still editing.
CHAT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{5,63}$")

ARCHIVE_DIR_NAME = ".archive"
JOURNAL_NAME = "journal.jsonl"
META_NAME = "meta.json"
STATE_NAME = "STATE.md"
STATE_HEAD_LINES = 40


def _workspaces_root() -> Path | None:
    value = getattr(host_config, "HOST_CHAT_ROOT", None)
    if value is None:
        return None
    return Path(value)


def _validate_chat_id(raw: str) -> str:
    value = raw.strip()
    if not CHAT_ID_PATTERN.fullmatch(value):
        raise CLIError(
            "Chat ids use 6-64 characters: letters, digits, dot, dash, underscore.",
            EXIT_USAGE,
        )
    return value


def _tree_stats(directory: Path) -> tuple[int, float]:
    total_bytes = 0
    latest = 0.0
    stack = [directory]
    while stack:
        current = stack.pop()
        try:
            latest = max(latest, current.lstat().st_mtime)
            for child in current.iterdir():
                info = child.lstat()
                latest = max(latest, info.st_mtime)
                if stat.S_ISREG(info.st_mode):
                    total_bytes += info.st_size
                elif stat.S_ISDIR(info.st_mode):
                    stack.append(child)
        except OSError:
            continue
    return total_bytes, latest


def _created_at(directory: Path) -> str | None:
    try:
        raw = (directory / META_NAME).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    try:
        meta = json.loads(raw.strip())
    except ValueError:
        return None
    if not isinstance(meta, dict) or not meta.get("created_at"):
        return None
    return str(meta["created_at"])


def _entry(directory: Path, *, archived: bool) -> dict[str, Any]:
    size, mtime = _tree_stats(directory)
    return {
        "chat_id": directory.name,
        "files": size,
        "created_at": _created_at(directory),
        "last_active": mtime,
        "archived": archived,
    }


def _inventory(root: Path) -> list[dict[str, Any]]:
    candidates: list[tuple[Path, bool]] = []
    try:
        children = sorted(root.iterdir(), key=lambda item: item.name)
    except OSError:
        return []
    for child in children:
        if not child.is_dir():
            continue
        if child.name == ARCHIVE_DIR_NAME:
            try:
                archived_children = sorted(
                    child.iterdir(), key=lambda item: item.name
                )
            except OSError:
                continue
            candidates.extend(
                (item, True) for item in archived_children if item.is_dir()
            )
        else:
            candidates.append((child, False))
    entries: list[dict[str, Any]] = []
    for directory, archived in candidates:
        entries.append(_entry(directory, archived=archived))
    entries.sort(key=lambda entry: (-entry["last_active"], entry["chat_id"]))
    return entries


def _state(entry: dict[str, Any]) -> str:
    # Position inside .archive is authoritative; missing-meta only describes
    # non-archived directories whose ownership metadata is absent/unreadable.
    if entry["archived"]:
        return "archived"
    if entry["created_at"] is None:
        return "missing-meta"
    return "active"


def _created_date(raw: str | None) -> str:
    if raw:
        try:
            return datetime.fromisoformat(raw).astimezone().strftime("%Y-%m-%d")
        except ValueError:
            pass
    return "-"


def _active_date(mtime: float) -> str:
    if mtime <= 0:
        return "-"
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")


def _created_iso(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return raw
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _list_workspaces(ctx: CLIContext) -> int:
    root = _workspaces_root()
    entries = _inventory(root) if root is not None and root.is_dir() else []

    if ctx.json_output:
        emit_json(
            [
                {
                    "chat_id": entry["chat_id"],
                    "files": entry["files"],
                    "created": _created_iso(entry["created_at"]),
                    "last_active": datetime.fromtimestamp(
                        max(entry["last_active"], 0.0), tz=timezone.utc
                    ).isoformat(),
                    "state": _state(entry),
                }
                for entry in entries
            ]
        )
        return 0

    renderer = renderer_for(ctx)
    if not entries:
        if ctx.quiet:
            return 0
        if root is None or not root.is_dir():
            renderer.summary("No chat workspace storage found yet.", "offline")
        else:
            renderer.summary(f"No chat workspaces under {root} yet.", "offline")
        return 0

    if ctx.quiet:
        emit_quiet([entry["chat_id"] for entry in entries])
        return 0

    rows = [
        [
            entry["chat_id"],
            entry["files"],
            _created_date(entry["created_at"]),
            _active_date(entry["last_active"]),
            _state(entry),
        ]
        for entry in entries
    ]
    renderer.header("Chat workspaces", f"{len(entries)} tracked under {root}")
    renderer.blank()
    renderer.table(
        ["CHAT_ID", "FILES", "CREATED", "LAST-ACTIVE", "STATE"],
        rows,
        numeric_columns=(1,),
    )
    renderer.blank()
    renderer.hint("bqa chats show <chat-id>", "Inspect one workspace with")
    return 0


def _journal_stats(workspace: Path) -> tuple[int, int]:
    started = 0
    completed = 0
    try:
        text = (workspace / JOURNAL_NAME).read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        return started, completed
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        if event_type == "op_started":
            started += 1
        elif event_type == "op_result":
            completed += 1
    return started, completed


def _resolve_workspace(chat_id: str) -> tuple[Path, bool] | None:
    root = _workspaces_root()
    if root is None:
        return None
    direct = root / chat_id
    archived = root / ARCHIVE_DIR_NAME / chat_id
    if direct.is_dir():
        return direct, False
    if archived.is_dir():
        return archived, True
    return None


def _show_workspace(ctx: CLIContext, raw_chat_id: str) -> int:
    chat_id = _validate_chat_id(raw_chat_id)
    resolved = _resolve_workspace(chat_id)
    if resolved is None:
        raise NotFoundCLIError(f"No chat workspace found for '{chat_id}'.")
    path, archived = resolved
    started, completed = _journal_stats(path)
    state_head: list[str] = []
    state_path = path / STATE_NAME
    if state_path.is_file():
        state_head = state_path.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()[:STATE_HEAD_LINES]

    if ctx.json_output:
        emit_json(
            {
                "path": str(path),
                "state_md_head": state_head,
                "journal": {"started": started, "completed": completed},
            }
        )
        return 0
    if ctx.quiet:
        emit_quiet(str(path))
        return 0

    renderer = renderer_for(ctx)
    renderer.header("Chat workspace", chat_id)
    renderer.blank()
    renderer.facts(
        [("Path", str(path)), ("State", "archived" if archived else "active")],
        no_wrap=("Path",),
    )
    if state_head:
        renderer.blank()
        renderer.section(STATE_NAME)
        for line in state_head:
            print(external_text(line, color_mode=ctx.color))
    renderer.blank()
    renderer.summary(f"Journal: {started} started · {completed} completed")
    renderer.hint(f"bqa chats show {chat_id} --json", "Machine-readable output with")
    return 0


def handle_chats(ctx: CLIContext, args) -> int:
    action = getattr(args, "chats_command", None) or "list"
    if action == "show":
        return _show_workspace(ctx, args.chat_id)
    return _list_workspaces(ctx)
