"""Private, bounded activity records for commands invoked through the MCP surface."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import BASE_DIR
from app.logging_audit import redact_sensitive_data

MCP_COMMAND_ACTIVITY_LOG = BASE_DIR / "logs" / "mcp_command_activity.jsonl"
_MAX_RECORD_BYTES = 48_000
_MAX_TEXT_CHARS = 12_000
_MAX_LOG_BYTES = 4_000_000
_ACTIVITY_LOCK = threading.Lock()


def _bounded_display_text(value: Any) -> tuple[str, bool]:
    text = str(redact_sensitive_data("" if value is None else str(value)))
    if len(text) <= _MAX_TEXT_CHARS:
        return text, False
    return text[:_MAX_TEXT_CHARS] + "\n... [ACTIVITY LOG TRUNCATED]", True


def _rotate_if_needed(path: Path) -> None:
    try:
        if path.exists() and path.stat().st_size >= _MAX_LOG_BYTES:
            backup = path.with_name(f"{path.name}.1")
            os.replace(path, backup)
    except OSError:
        # An unavailable activity log must never interrupt a host command.
        return


def record_mcp_command_activity(
    *,
    command: str,
    cwd: str,
    result: dict[str, Any],
    chat_id: str | None = None,
    operation_id: str | None = None,
    phase: str | None = None,
    status: str | None = None,
) -> None:
    """Append a redacted command/result record for the local desktop UI.

    This journal intentionally records only commands dispatched by the MCP tool
    path. It is bounded, stored with mode 0600, and is independent from the
    security audit log, whose command fields remain hashes only.
    """
    command_text, command_truncated = _bounded_display_text(command)
    stdout, stdout_limited = _bounded_display_text(result.get("stdout", ""))
    stderr, stderr_limited = _bounded_display_text(result.get("stderr", ""))
    record = {
        "schema_version": 1,
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "mcp",
        "tool": "host_run_command",
        "command": command_text,
        "command_truncated": command_truncated,
        "cwd": _bounded_display_text(cwd)[0],
        "ok": bool(result.get("ok", False)),
        "exit_code": result.get("exit_code"),
        "timed_out": bool(result.get("timed_out", False)),
        "duration_ms": result.get("duration_ms"),
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": bool(result.get("stdout_truncated", False)) or stdout_limited,
        "stderr_truncated": bool(result.get("stderr_truncated", False)) or stderr_limited,
    }
    if chat_id:
        # The command transcript is already a local 0600 operator journal.
        # Keep the opaque chat id beside it so the desktop UI can group calls
        # by the workplace folder that initiated them.
        record["chat_id"] = str(chat_id)
    if operation_id:
        record["operation_id"] = str(operation_id)
    if phase:
        record["phase"] = str(phase)
    if status:
        record["status"] = str(status)
    encoded = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    if len(encoded) > _MAX_RECORD_BYTES:  # pragma: no cover - defensive cap
        return

    with _ACTIVITY_LOCK:
        try:
            path = MCP_COMMAND_ACTIVITY_LOG
            path.parent.mkdir(parents=True, exist_ok=True)
            _rotate_if_needed(path)
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(descriptor, encoded)
            finally:
                os.close(descriptor)
            os.chmod(path, 0o600)
        except OSError:
            # Activity history is an observability aid, never a command dependency.
            return


def read_mcp_command_activity(limit: int = 20) -> list[dict[str, Any]]:
    """Return newest-first bounded records created by the MCP command tool."""
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100.")
    try:
        lines = MCP_COMMAND_ACTIVITY_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    records: list[dict[str, Any]] = []
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(item, dict)
            and item.get("schema_version") == 1
            and item.get("source") == "mcp"
            and item.get("tool") == "host_run_command"
        ):
            records.append(item)
    return list(reversed(records[-limit:]))
