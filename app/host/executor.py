from __future__ import annotations

import hashlib
import os
import signal
import shutil
import subprocess  # nosec B404
import threading
import time
import uuid
from typing import Any, BinaryIO, Callable, Optional

import app.config
from app.error_contract import ServiceBusyError
from app.host.paths import display_host_path, resolve_host_path
from app.host.policy import require_host_command_allowed
from app.logging_audit import log_audit_event
from app.activity_log import record_mcp_command_activity


_ALWAYS_STRIP_ENV = {
    "BASH_ENV",
    "ENV",
    "CDPATH",
    "GLOBIGNORE",
    "LD_AUDIT",
    "LD_PRELOAD",
    "PYTHONINSPECT",
}
_SENSITIVE_ENV_MARKERS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "API_KEY",
    "PRIVATE_KEY",
    "ACCESS_KEY",
    "SESSION_KEY",
    "AUTH_COOKIE",
)
_BASH_PATH = shutil.which("bash") or "/bin/bash"
_BASE_ENV_KEYS = {
    "HOME",
    "LANG",
    "LC_ALL",
    "LOGNAME",
    "PATH",
    "SHELL",
    "TERM",
    "TMPDIR",
    "USER",
}


class CommandCapacity:
    """Bound concurrent command processes and their queue wait time."""

    def __init__(self, max_concurrent: int, queue_timeout_seconds: float):
        self.max_concurrent = max(1, int(max_concurrent))
        self.queue_timeout_seconds = max(0.0, float(queue_timeout_seconds))
        self._condition = threading.Condition()
        self._active = 0
        self._queued = 0
        self._peak_active = 0
        self._started = 0
        self._rejected = 0

    def acquire(self) -> None:
        deadline = time.monotonic() + self.queue_timeout_seconds
        with self._condition:
            if self._active >= self.max_concurrent:
                self._queued += 1
                try:
                    while self._active >= self.max_concurrent:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0 or not self._condition.wait(timeout=remaining):
                            self._rejected += 1
                            raise ServiceBusyError(
                                "Command execution capacity is currently full."
                            )
                finally:
                    self._queued -= 1
            self._active += 1
            self._started += 1
            self._peak_active = max(self._peak_active, self._active)

    def release(self) -> None:
        with self._condition:
            if self._active > 0:
                self._active -= 1
            self._condition.notify()

    def get_stats(self) -> dict[str, Any]:
        with self._condition:
            return {
                "max_concurrent": self.max_concurrent,
                "queue_timeout_seconds": self.queue_timeout_seconds,
                "active": self._active,
                "queued": self._queued,
                "peak_active": self._peak_active,
                "started": self._started,
                "rejected": self._rejected,
            }


command_capacity = CommandCapacity(
    app.config.MAX_CONCURRENT_COMMANDS,
    app.config.COMMAND_QUEUE_TIMEOUT_SECONDS,
)


def _build_environment() -> dict[str, str]:
    explicit = set(app.config.HOST_ENV_ALLOWLIST)
    if app.config.HOST_INHERIT_ENV:
        environment = dict(os.environ)
        for key in list(environment):
            if key in _ALWAYS_STRIP_ENV:
                environment.pop(key, None)
        return environment

    allowed = _BASE_ENV_KEYS | explicit
    return {
        key: value
        for key, value in os.environ.items()
        if key in allowed and key not in _ALWAYS_STRIP_ENV
    }


def _drain_limited(pipe: BinaryIO, max_bytes: int, result: dict[str, Any]) -> None:
    stored = bytearray()
    truncated = False
    try:
        while True:
            chunk = pipe.read(64 * 1024)
            if not chunk:
                break
            remaining = max_bytes - len(stored)
            if remaining > 0:
                stored.extend(chunk[:remaining])
            if len(chunk) > max(0, remaining):
                truncated = True
    finally:
        pipe.close()
    text = bytes(stored).decode("utf-8", errors="replace")
    if truncated:
        text += "\n... [TRUNCATED]"
    result["text"] = text
    result["truncated"] = truncated


def _terminate_process_group(process: subprocess.Popen[bytes]) -> int:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        return process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return process.wait(timeout=2)


def _execute_host_command_impl(
    command: str,
    *,
    cwd: Optional[str] = None,
    timeout_seconds: Optional[int] = None,
    on_started: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Execute a command with bounded output, sanitized environment, and cleanup."""
    max_allowed = getattr(app.config, "MAX_TIMEOUT_SECONDS", 36000)
    default_timeout = getattr(app.config, "DEFAULT_TIMEOUT_SECONDS", 300)

    if timeout_seconds is None:
        wait_timeout: int | None = min(default_timeout, max_allowed) if max_allowed > 0 else default_timeout
        if wait_timeout is not None and wait_timeout <= 0:
            wait_timeout = None
    elif not isinstance(timeout_seconds, int):
        raise TypeError("timeout_seconds must be an integer")
    elif timeout_seconds < 0:
        raise ValueError("timeout_seconds cannot be negative (use 0 to disable timeout)")
    elif timeout_seconds == 0:
        wait_timeout = None
    else:
        if max_allowed > 0 and timeout_seconds > max_allowed:
            raise ValueError(
                f"timeout_seconds must be between 0 and {max_allowed} (0 to disable timeout)"
            )
        wait_timeout = timeout_seconds


    policy = require_host_command_allowed(command)
    resolved_cwd = resolve_host_path(
        cwd or ".",
        must_exist=True,
        expect_directory=True,
    )
    command_hash = hashlib.sha256(command.encode("utf-8")).hexdigest()
    started = time.monotonic()

    if on_started is not None:
        on_started(display_host_path(resolved_cwd))

    process = subprocess.Popen(  # nosec B603
        [_BASH_PATH, "--noprofile", "--norc", "-c", command],
        cwd=resolved_cwd,
        env=_build_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    if process.stdout is None or process.stderr is None:  # pragma: no cover
        process.kill()
        raise RuntimeError("Unable to capture command output streams.")

    stdout_result: dict[str, Any] = {}
    stderr_result: dict[str, Any] = {}
    stdout_thread = threading.Thread(
        target=_drain_limited,
        args=(process.stdout, app.config.MAX_OUTPUT_BYTES, stdout_result),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_drain_limited,
        args=(process.stderr, app.config.MAX_OUTPUT_BYTES, stderr_result),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    timed_out = False
    try:
        exit_code = process.wait(timeout=wait_timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        exit_code = _terminate_process_group(process)
    finally:
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)
        if stdout_thread.is_alive() or stderr_thread.is_alive():
            _terminate_process_group(process)
            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)
    output_incomplete = stdout_thread.is_alive() or stderr_thread.is_alive()

    stdout = str(stdout_result.get("text", ""))
    stderr = str(stderr_result.get("text", ""))
    stdout_truncated = bool(stdout_result.get("truncated", False))
    stderr_truncated = bool(stderr_result.get("truncated", False))
    duration_ms = int((time.monotonic() - started) * 1000)

    log_audit_event(
        "HOST_COMMAND",
        {
            "command_sha256": command_hash,
            "command_names": policy.get("command_names", []),
            "cwd": str(resolved_cwd),
            "exit_code": exit_code,
            "timed_out": timed_out,
            "duration_ms": duration_ms,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        },
    )

    base_result = {
        "command_sha256": command_hash,
        "cwd": display_host_path(resolved_cwd),
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "output_incomplete": output_incomplete,
        "duration_ms": duration_ms,
        "timed_out": timed_out,
        "policy": policy,
    }
    if timed_out:
        return {
            "ok": False,
            "error": {
                "code": "TIMEOUT",
                "message": f"Host command timed out after {wait_timeout} seconds.",
            },
            **base_result,
        }
    return {"ok": exit_code == 0, **base_result}


def execute_host_command(
    command: str,
    *,
    cwd: Optional[str] = None,
    timeout_seconds: Optional[int] = None,
    activity_source: str | None = None,

    activity_chat_id: str | None = None,
    activity_operation_id: str | None = None,
) -> dict[str, Any]:
    """Execute a host command within the configured concurrency capacity."""
    command_capacity.acquire()
    activity_started = time.monotonic()
    operation_id = (
        activity_operation_id or f"act-{uuid.uuid4().hex}"
        if activity_source == "mcp"
        else None
    )
    started_cwd: str | None = None

    def record_activity(
        *, cwd_value: str, result_value: dict[str, Any], phase: str, status: str
    ) -> None:
        if activity_source != "mcp":
            return
        record_mcp_command_activity(
            command=command,
            cwd=cwd_value,
            chat_id=activity_chat_id,
            operation_id=operation_id,
            phase=phase,
            status=status,
            result=result_value,
        )

    def record_started(resolved_cwd: str) -> None:
        nonlocal started_cwd
        started_cwd = resolved_cwd
        record_activity(
            cwd_value=resolved_cwd,
            result_value={"ok": False, "stdout": "", "stderr": ""},
            phase="started",
            status="running",
        )

    try:
        try:
            result = _execute_host_command_impl(
                command,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
                on_started=record_started if activity_source == "mcp" else None,
            )
        except Exception as exc:
            record_activity(
                cwd_value=started_cwd or cwd or ".",
                result_value={
                    "ok": False,
                    "stderr": str(exc),
                    "duration_ms": int((time.monotonic() - activity_started) * 1000),
                },
                phase="completed",
                status="failed",
            )
            raise
        status = (
            "timed_out"
            if result.get("timed_out")
            else "succeeded"
            if result.get("ok")
            else "failed"
        )
        record_activity(
            cwd_value=str(result.get("cwd", cwd or ".")),
            result_value=result,
            phase="completed",
            status=status,
        )
        return result
    finally:
        command_capacity.release()
