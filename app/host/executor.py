from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

import app.config
from app.host.paths import display_host_path, resolve_host_path
from app.host.policy import require_host_command_allowed
from app.logging_audit import log_audit_event


def _read_limited(stream, max_bytes: int) -> tuple[str, bool]:
    stream.seek(0)
    raw = stream.read(max_bytes + 1)
    truncated = len(raw) > max_bytes
    raw = raw[:max_bytes]
    text = raw.decode("utf-8", errors="replace")
    if truncated:
        text += "\n... [TRUNCATED]"
    return text, truncated


def _build_environment() -> dict[str, str]:
    if app.config.HOST_INHERIT_ENV:
        return dict(os.environ)

    allowed = {
        "HOME",
        "LANG",
        "LC_ALL",
        "LOGNAME",
        "PATH",
        "SHELL",
        "TERM",
        "TMPDIR",
        "USER",
    } | set(app.config.HOST_ENV_ALLOWLIST)
    return {key: value for key, value in os.environ.items() if key in allowed}


def execute_host_command(
    command: str,
    *,
    cwd: Optional[str] = None,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Execute a command on the host with bounded output and process cleanup."""
    if not isinstance(timeout_seconds, int):
        raise TypeError("timeout_seconds must be an integer")
    if timeout_seconds < 1 or timeout_seconds > app.config.MAX_TIMEOUT_SECONDS:
        raise ValueError(
            f"timeout_seconds must be between 1 and {app.config.MAX_TIMEOUT_SECONDS}"
        )

    policy = require_host_command_allowed(command)
    resolved_cwd = resolve_host_path(
        cwd or ".",
        must_exist=True,
        expect_directory=True,
    )
    command_hash = hashlib.sha256(command.encode("utf-8")).hexdigest()
    started = time.monotonic()

    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        process = subprocess.Popen(
            ["bash", "-lc", command],
            cwd=resolved_cwd,
            env=_build_environment(),
            stdout=stdout_file,
            stderr=stderr_file,
            start_new_session=True,
        )
        timed_out = False
        try:
            exit_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                exit_code = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                exit_code = process.wait(timeout=2)

        stdout, stdout_truncated = _read_limited(
            stdout_file, app.config.MAX_OUTPUT_BYTES
        )
        stderr, stderr_truncated = _read_limited(
            stderr_file, app.config.MAX_OUTPUT_BYTES
        )

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
        },
    )

    if timed_out:
        return {
            "ok": False,
            "error": {
                "code": "TIMEOUT",
                "message": f"Host command timed out after {timeout_seconds} seconds.",
            },
            "command_sha256": command_hash,
            "cwd": display_host_path(resolved_cwd),
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "duration_ms": duration_ms,
            "policy": policy,
        }

    return {
        "ok": exit_code == 0,
        "command_sha256": command_hash,
        "cwd": display_host_path(resolved_cwd),
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "duration_ms": duration_ms,
        "policy": policy,
    }
