"""Private, bounded activity records for commands invoked through the MCP surface."""

from __future__ import annotations

import json
import os
import threading
import tempfile
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
_MAX_ACTIVITY_OUTPUT_BYTES = 16_000_000
_ACTIVITY_LOCK = threading.Lock()


def _redacted_display_text(value: Any) -> str:
    return str(
        redact_sensitive_data("" if value is None else str(value), truncate=False)
    )


def _bounded_display_text(value: Any) -> tuple[str, bool]:
    text = _redacted_display_text(value)
    if len(text) <= _MAX_TEXT_CHARS:
        return text, False
    return text[:_MAX_TEXT_CHARS] + "\n... [ACTIVITY LOG TRUNCATED]", True


def _activity_output_dir(path: Path) -> Path:
    return path.with_name(f"{path.stem}_output")


def _activity_output_path(path: Path, event_id: str) -> Path | None:
    try:
        normalized = str(uuid.UUID(event_id))
    except (AttributeError, TypeError, ValueError):
        return None
    return _activity_output_dir(path) / f"{normalized}.json"


def _clear_activity_outputs(path: Path) -> None:
    output_dir = _activity_output_dir(path)
    try:
        for child in output_dir.iterdir():
            if child.is_file():
                child.unlink()
        output_dir.rmdir()
    except OSError:
        return


def _activity_output_bytes(path: Path) -> int:
    try:
        return sum(
            child.stat().st_size
            for child in _activity_output_dir(path).iterdir()
            if child.is_file()
        )
    except OSError:
        return 0


def _delete_activity_output(path: Path, event_id: str) -> None:
    output_path = _activity_output_path(path, event_id)
    if output_path is None:
        return
    try:
        output_path.unlink(missing_ok=True)
        output_path.parent.rmdir()
    except OSError:
        return


def _rotate_if_needed(path: Path, *, pending_output_bytes: int = 0) -> None:
    try:
        journal_full = path.exists() and path.stat().st_size >= _MAX_LOG_BYTES
        outputs_full = (
            _activity_output_bytes(path) + pending_output_bytes
            > _MAX_ACTIVITY_OUTPUT_BYTES
        )
        if journal_full or outputs_full:
            if path.exists():
                backup = path.with_name(f"{path.name}.1")
                os.replace(path, backup)
            _clear_activity_outputs(path)
    except OSError:
        # An unavailable activity log must never interrupt a host command.
        return


def _write_activity_output(
    path: Path, event_id: str, *, stdout: str, stderr: str
) -> bool:
    output_path = _activity_output_path(path, event_id)
    if output_path is None:
        return False
    encoded = json.dumps(
        {"stdout": stdout, "stderr": stderr}, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    temporary_name = ""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(output_path.parent, 0o700)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=output_path.parent, prefix=f".{event_id}.", suffix=".tmp"
        )
        with os.fdopen(descriptor, "wb") as output_file:
            os.fchmod(output_file.fileno(), 0o600)
            output_file.write(encoded)
            output_file.flush()
            os.fsync(output_file.fileno())
        os.replace(temporary_name, output_path)
        os.chmod(output_path, 0o600)
        return True
    except OSError:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
        return False


def _read_activity_output(path: Path, event_id: Any) -> dict[str, str] | None:
    output_path = _activity_output_path(path, str(event_id or ""))
    if output_path is None:
        return None
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    stdout, stderr = payload.get("stdout"), payload.get("stderr")
    if not isinstance(stdout, str) or not isinstance(stderr, str):
        return None
    return {"stdout": stdout, "stderr": stderr}


def _write_all(descriptor: int, data: bytes) -> None:
    """Write a complete journal line even when the OS accepts a short write."""
    remaining = memoryview(data)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise OSError("Unable to write activity journal entry")
        remaining = remaining[written:]


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
    stdout_text = _redacted_display_text(result.get("stdout", ""))
    stderr_text = _redacted_display_text(result.get("stderr", ""))
    event_id = str(uuid.uuid4())
    stdout, stderr = "", ""
    stdout_limited = stderr_limited = False
    record = {
        "schema_version": 1,
        "event_id": event_id,
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
    with _ACTIVITY_LOCK:
        attachment_written = False
        try:
            path = MCP_COMMAND_ACTIVITY_LOG
            path.parent.mkdir(parents=True, exist_ok=True)
            pending_output_bytes = len(
                json.dumps(
                    {"stdout": stdout_text, "stderr": stderr_text},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            _rotate_if_needed(path, pending_output_bytes=pending_output_bytes)
            if stdout_text or stderr_text:
                if _write_activity_output(
                    path, event_id, stdout=stdout_text, stderr=stderr_text
                ):
                    record["output_ref"] = event_id
                    attachment_written = True
                else:
                    stdout, stdout_limited = _bounded_display_text(stdout_text)
                    stderr, stderr_limited = _bounded_display_text(stderr_text)
                    record["stdout"] = stdout
                    record["stderr"] = stderr
                    record["stdout_truncated"] = (
                        bool(result.get("stdout_truncated", False)) or stdout_limited
                    )
                    record["stderr_truncated"] = (
                        bool(result.get("stderr_truncated", False)) or stderr_limited
                    )
            encoded = (
                json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            ).encode("utf-8")
            if len(encoded) > _MAX_RECORD_BYTES:  # pragma: no cover - defensive cap
                if attachment_written:
                    _delete_activity_output(path, event_id)
                return
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                offset = os.lseek(descriptor, 0, os.SEEK_END)
                try:
                    _write_all(descriptor, encoded)
                except OSError:
                    os.ftruncate(descriptor, offset)
                    raise
            finally:
                os.close(descriptor)
            os.chmod(path, 0o600)
        except OSError:
            if attachment_written:
                _delete_activity_output(MCP_COMMAND_ACTIVITY_LOG, event_id)
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
            output = _read_activity_output(
                MCP_COMMAND_ACTIVITY_LOG, item.get("output_ref")
            )
            if output is not None:
                item = {**item, **output}
            records.append(item)
    return list(reversed(records[-limit:]))
