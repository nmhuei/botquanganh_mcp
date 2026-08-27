from __future__ import annotations

import json
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import chat_sweeper
from app import config as host_config
from app.chat_workspace import read_journal_records, summarize_journal_records
from app.cli.context import CLIContext
from app.cli.errors import EXIT_USAGE, CLIError, NotFoundCLIError
from app.cli.output import emit_json, emit_quiet, external_text, renderer_for

# Verbatim chat-id contract, kept local so this read-only view never imports
# the workspace modules their owners are still editing.
CHAT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{5,63}$")

ARCHIVE_DIR_NAME = ".archive"
JOURNAL_NAME = "journal.jsonl"
META_NAME = "meta.json"
STATE_NAME = "STATE.md"
STATE_HEAD_LINES = 40
SEVERITY_RANK = {"DEBUG": 5, "INFO": 9, "WARN": 13, "ERROR": 17}


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
    return datetime.fromtimestamp(mtime, tz=timezone.utc).astimezone().strftime("%Y-%m-%d")


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
    for event in read_journal_records(workspace):
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


def _workspace_log_detail(item: dict[str, Any]) -> str:
    payload = item.get("payload")
    if not isinstance(payload, dict):
        return "-"
    for key in ("path", "cwd", "query", "intent", "exit_code", "size_bytes"):
        value = payload.get(key)
        if value not in (None, ""):
            text = f"{key}={value}"
            return text if len(text) <= 72 else text[:69] + "..."
    command_hash = payload.get("command_sha256")
    if isinstance(command_hash, str) and command_hash:
        return f"command_sha256={command_hash[:12]}…"
    return "-"


def _workspace_logs(
    ctx: CLIContext,
    raw_chat_id: str,
    *,
    severity: str | None,
    min_severity: str | None,
    category: str | None,
    outcome: str | None,
    action: str | None,
    phase: str | None,
    limit: int,
) -> int:
    chat_id = _validate_chat_id(raw_chat_id)
    if limit < 1 or limit > 1000:
        raise CLIError("--limit must be between 1 and 1000.", EXIT_USAGE)
    resolved = _resolve_workspace(chat_id)
    if resolved is None:
        raise NotFoundCLIError(f"No chat workspace found for '{chat_id}'.")
    path, archived = resolved
    records = read_journal_records(path)
    if severity:
        wanted = severity.upper()
        records = [item for item in records if item.get("severity_text") == wanted]
    if min_severity:
        floor = SEVERITY_RANK[min_severity.upper()]
        records = [
            item
            for item in records
            if int(item.get("severity_number") or 0) >= floor
        ]
    if category:
        wanted_category = category.lower()
        records = [
            item
            for item in records
            if str(item.get("event_category") or "").lower() == wanted_category
        ]
    if outcome:
        records = [item for item in records if item.get("event_outcome") == outcome]
    if action:
        wanted_action = action.lower()
        records = [
            item
            for item in records
            if str(item.get("event_action") or "").lower() == wanted_action
        ]
    if phase:
        records = [item for item in records if item.get("operation_phase") == phase]
    records = records[-limit:]
    summary = summarize_journal_records(records)
    payload = {
        "chat_id": chat_id,
        "path": str(path),
        "state": "archived" if archived else "active",
        "count": len(records),
        "summary": summary,
        "records": records,
    }
    if ctx.json_output:
        emit_json(payload)
        return 0
    if ctx.quiet:
        emit_quiet(
            [
                "{seq} {severity} {category} {action} {outcome} {phase}".format(
                    seq=item.get("seq", "?"),
                    severity=item.get("severity_text", "INFO"),
                    category=item.get("event_category", "api"),
                    action=item.get("event_action", item.get("kind", "?")),
                    outcome=item.get("event_outcome", "unknown"),
                    phase=item.get("operation_phase", "event"),
                )
                for item in records
            ]
        )
        return 0

    renderer = renderer_for(ctx)
    renderer.header("Chat workspace logs", chat_id)
    renderer.summary(
        "{events} event(s) · {ops} completed · {failures} failed · {path}".format(
            events=len(records),
            ops=summary.get("operations", 0),
            failures=summary.get("failures", 0),
            path=path,
        )
    )
    if not records:
        return 0
    rows = [
        [
            item.get("seq", "?"),
            str(item.get("ts", "-")),
            item.get("severity_text", "INFO"),
            item.get("event_category", "api"),
            item.get("event_action", item.get("kind", "?")),
            item.get("event_outcome", "unknown"),
            item.get("event_duration_ms", "-"),
            _workspace_log_detail(item),
        ]
        for item in records
    ]
    renderer.blank()
    renderer.table(
        ["SEQ", "TIME", "SEVERITY", "CATEGORY", "ACTION", "OUTCOME", "MS", "DETAIL"],
        rows,
        numeric_columns=(0, 6),
    )
    return 0


def _emit_action_result(ctx: CLIContext, result: dict[str, Any]) -> int:
    if ctx.json_output:
        emit_json(result)
    elif ctx.quiet:
        emit_quiet(str(result.get("status", "")))
    else:
        renderer = renderer_for(ctx)
        renderer.summary(
            f"{result.get('status', 'unknown')}: {result.get('target', '-')}",
            "success" if result.get("status") in {"archived", "restored", "deleted"} else "warning",
        )
    return 0


def _archive_workspace(ctx: CLIContext, raw_chat_id: str) -> int:
    chat_id = _validate_chat_id(raw_chat_id)
    resolved = _resolve_workspace(chat_id)
    if resolved is None:
        raise NotFoundCLIError(f"No chat workspace found for '{chat_id}'.")
    path, archived = resolved
    if archived:
        raise CLIError(f"Chat workspace '{chat_id}' is already archived.", EXIT_USAGE)
    root = _workspaces_root()
    assert root is not None
    result = chat_sweeper.apply_actions(
        [{"action": "ARCHIVE_IDLE", "target": str(path)}], root, dry_run=False
    )[0]
    if result.get("status") != "archived":
        raise CLIError(str(result.get("detail") or "Archive failed."))
    return _emit_action_result(ctx, result)


def _restore_workspace(ctx: CLIContext, raw_chat_id: str) -> int:
    chat_id = _validate_chat_id(raw_chat_id)
    root = _workspaces_root()
    if root is None:
        raise NotFoundCLIError(f"No chat workspace found for '{chat_id}'.")
    source = root / ARCHIVE_DIR_NAME / chat_id
    destination = root / chat_id
    if destination.exists():
        raise CLIError(f"Active workspace '{chat_id}' already exists.", EXIT_USAGE)
    if not source.is_dir():
        raise NotFoundCLIError(f"No archived workspace found for '{chat_id}'.")
    try:
        source.rename(destination)
    except OSError as exc:
        raise CLIError(f"Restore failed: {exc}") from exc
    return _emit_action_result(
        ctx,
        {"action": "RESTORE", "target": str(source), "destination": str(destination), "status": "restored"},
    )


def _delete_workspace(ctx: CLIContext, raw_chat_id: str, *, confirmed: bool) -> int:
    chat_id = _validate_chat_id(raw_chat_id)
    if not confirmed:
        raise CLIError("Permanent deletion requires --yes.", EXIT_USAGE)
    root = _workspaces_root()
    if root is None:
        raise NotFoundCLIError(f"No archived workspace found for '{chat_id}'.")
    target = root / ARCHIVE_DIR_NAME / chat_id
    if not target.is_dir():
        raise NotFoundCLIError(f"No archived workspace found for '{chat_id}'.")
    result = chat_sweeper.apply_actions(
        [{"action": "DELETE_EXPIRED", "target": str(target)}], root, dry_run=False
    )[0]
    if result.get("status") != "deleted":
        raise CLIError(str(result.get("detail") or "Delete failed."))
    return _emit_action_result(ctx, result)


def _sweep_limits() -> chat_sweeper.SweepLimits:
    return chat_sweeper.SweepLimits(
        idle_archive_hours=float(getattr(host_config, "HOST_CHAT_IDLE_ARCHIVE_HOURS", 72)),
        retention_days=float(getattr(host_config, "HOST_CHAT_RETENTION_DAYS", 30)),
        max_workspaces=int(getattr(host_config, "HOST_CHAT_MAX_WORKSPACES", 128)),
        root_max_gb=float(getattr(host_config, "HOST_CHAT_ROOT_MAX_GB", 24)),
    )


def _prune_workspaces(ctx: CLIContext, *, apply: bool) -> int:
    root = _workspaces_root()
    inventory = chat_sweeper.scan(root) if root is not None else []
    actions = chat_sweeper.plan_actions(inventory, _sweep_limits())
    results = chat_sweeper.apply_actions(actions, root, dry_run=not apply) if root is not None else []
    payload = {"apply": apply, "planned": actions, "results": results}
    if ctx.json_output:
        emit_json(payload)
    elif ctx.quiet:
        emit_quiet(str(len(actions)))
    else:
        renderer = renderer_for(ctx)
        renderer.header("Chat workspace prune", "apply" if apply else "dry-run")
        renderer.summary(f"{len(actions)} lifecycle action(s) planned")
        for result in results:
            renderer.facts([("Action", str(result.get("action"))), ("Status", str(result.get("status"))), ("Target", str(result.get("target")))], no_wrap=("Target",))
    return 0


def _workspace_stats(ctx: CLIContext) -> int:
    root = _workspaces_root()
    entries = _inventory(root) if root is not None and root.is_dir() else []
    active = [entry for entry in entries if not entry["archived"]]
    archived = [entry for entry in entries if entry["archived"]]
    total_bytes = sum(int(entry["files"]) for entry in entries)
    payload = {
        "active": len(active),
        "archived": len(archived),
        "total": len(entries),
        "bytes": total_bytes,
        "root": str(root) if root is not None else None,
    }
    if ctx.json_output:
        emit_json(payload)
    elif ctx.quiet:
        emit_quiet(str(len(entries)))
    else:
        renderer = renderer_for(ctx)
        renderer.header("Chat workspace stats")
        renderer.facts(
            [("Active", len(active)), ("Archived", len(archived)), ("Total", len(entries)), ("Bytes", total_bytes), ("Root", str(root) if root is not None else "-")],
            no_wrap=("Root",),
        )
    return 0


def handle_chats(ctx: CLIContext, args) -> int:
    action = getattr(args, "chats_command", None) or "list"
    if action == "show":
        return _show_workspace(ctx, args.chat_id)
    if action == "logs":
        return _workspace_logs(
            ctx,
            args.chat_id,
            severity=args.severity,
            min_severity=args.min_severity,
            category=args.category,
            outcome=args.outcome,
            action=args.action,
            phase=args.phase,
            limit=args.limit,
        )
    if action == "archive":
        return _archive_workspace(ctx, args.chat_id)
    if action == "restore":
        return _restore_workspace(ctx, args.chat_id)
    if action == "delete":
        return _delete_workspace(ctx, args.chat_id, confirmed=args.yes)
    if action == "prune":
        return _prune_workspaces(ctx, apply=args.apply)
    if action == "stats":
        return _workspace_stats(ctx)
    return _list_workspaces(ctx)
