"""Unified terminal execution tool: robust process group management and error intelligence.

Consolidates command execution and inspection into a single evolved super-tool.
Adheres to the user's maximum-freedom policy (no command blacklist, permits sudo/pentest tools)
while protecting host stability via process group isolation (SIGKILL on timeout),
non-interactive stdin guards (subprocess.DEVNULL), and middle-truncation for output buffers.
"""

from __future__ import annotations

import asyncio
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

import app.config
from app.host.paths import display_host_path, resolve_host_path
from app.task_manager import get_task_manager
from app.mcp_server import mcp
from app.security import format_error_response
from app.tools_common import (
    _begin_workspace_journal,
    _finish_workspace_journal,
    _guard_chat_id,
    _record_tool_call,
    enforce_payload,
)

_DEFAULT_TIMEOUT = getattr(app.config, "DEFAULT_TIMEOUT_SECONDS", 60)
_MAX_TIMEOUT = getattr(app.config, "MAX_TIMEOUT_SECONDS", 300)
_MAX_OUTPUT_BYTES = 500_000  # Strict 500KB cap to ensure serialized JSON stays under 512KB

_ERROR_PATTERNS = [
    re.compile(r"Traceback \(most recent call last\):[\s\S]+?(?=\n\S|\Z)"),
    re.compile(r"^[A-Za-z0-9_]+Error:.*$", re.MULTILINE),
    re.compile(r"^.*fatal error:.*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^.*undefined reference to.*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^.*panic:.*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^.*Segmentation fault.*$", re.MULTILINE | re.IGNORECASE),
]


def _truncate_output(text: str, max_bytes: Optional[int] = None) -> tuple[str, bool]:
    if max_bytes is None:
        max_bytes = _MAX_OUTPUT_BYTES
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text, False

    lines = text.splitlines()
    head_count = 100
    tail_count = 100
    filter_hint = (
        "Output exceeded 512KB bridge ceiling. Actionable recommendation: "
        "Pipe through Unix filters: `| head -n 100`, `| grep <pattern>`, `| tail -n 100`, "
        "or redirect to file `> /tmp/output.log` and inspect using `workspace_explore`."
    )

    if len(lines) <= (head_count + tail_count):
        safe_slice = encoded[:max_bytes].decode("utf-8", errors="replace")
        return safe_slice + f"\n\n[TRUNCATED] {filter_hint}", True

    head = lines[:head_count]
    tail = lines[-tail_count:]
    head_bytes = len("\n".join(head).encode("utf-8"))
    tail_bytes = len("\n".join(tail).encode("utf-8"))
    removed_bytes = len(encoded) - (head_bytes + tail_bytes)

    result = (
        "\n".join(head)
        + f"\n\n[TRUNCATED {max(0, removed_bytes):,} BYTES] {filter_hint}\n\n"
        + "\n".join(tail)
    )
    return result, True


def _extract_semantic_errors(output: str) -> list[str]:
    found_errors: list[str] = []
    for pattern in _ERROR_PATTERNS:
        matches = pattern.findall(output)
        for match in matches:
            cleaned = match.strip()
            if cleaned and cleaned not in found_errors:
                found_errors.append(cleaned[:300])
            if len(found_errors) >= 10:
                break
        if len(found_errors) >= 10:
            break
    return found_errors


def _kill_process_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def _run_async_task(coro, timeout: float | None = None):
    from app.task_manager import run_task_coro

    return run_task_coro(coro, timeout=timeout)


@mcp.tool(
    name="terminal_execute",
    description=(
        "Unified terminal execution super-tool. Executes shell commands directly in bash "
        "with process-group isolation and non-interactive protection. "
        "Unrestricted execution mode: allows research, compilation, and administrative commands. "
        "Requires an attributable chat_id in enforce mode."
    ),
)
def terminal_execute(
    command: str,
    timeout_seconds: Optional[int] = None,
    cwd: Optional[str] = None,
    chat_id: Optional[str] = None,
    wait_ms_before_async: int = getattr(app.config, "HOST_TASK_WAIT_BEFORE_ASYNC_MS", 5000),
    background: bool | None = None,
) -> dict[str, Any]:
    """Execute commands with adaptive asynchronous task handling."""
    validated, rejection = _guard_chat_id("terminal_execute", chat_id)
    if rejection is not None:
        return rejection

    resolved_cwd = resolve_host_path(cwd) if cwd else app.config.HOST_DEFAULT_DIR
    resolved_cwd.mkdir(parents=True, exist_ok=True)
    command_summary = command.strip()
    manager = get_task_manager()

    if background is True:
        task_id = _run_async_task(
            manager.spawn_process(["/bin/bash", "-lc", command], str(resolved_cwd), validated or "default")
        )
        return {
            "ok": True,
            "task_id": task_id,
            "detached": True,
            "command_summary": command_summary,
            "message": "Task moved to background.",
        }

    # Adaptive detach mode: activated when caller specifies custom wait_ms_before_async
    is_explicit_adaptive = wait_ms_before_async != getattr(app.config, "HOST_TASK_WAIT_BEFORE_ASYNC_MS", 5000)
    if is_explicit_adaptive and timeout_seconds is None and background is not False:
        t0 = time.monotonic()
        task_id = _run_async_task(
            manager.spawn_process(["/bin/bash", "-lc", command], str(resolved_cwd), validated or "default")
        )
        try:
            status = _run_async_task(manager.wait_task(task_id, timeout=wait_ms_before_async / 1000.0))
        except (TimeoutError, asyncio.TimeoutError):
            return {
                "ok": True,
                "task_id": task_id,
                "detached": True,
                "command_summary": command_summary,
                "initial_tail": _run_async_task(manager.tail_task(task_id, lines=50)),
                "message": "Command exceeded synchronous threshold. Detached to background task. Use task(action='wait', task_id=...) to await completion, or task(action='tail') to inspect output. DO NOT poll status in a loop.",
            }
        exit_code = status.get("exit_code", 0)
        raw_output = _run_async_task(manager.tail_task(task_id, lines=10000))
        truncated_output, was_truncated = _truncate_output(raw_output)
        semantic_errors = _extract_semantic_errors(raw_output)
        return {
            "ok": exit_code == 0,
            "exit_code": exit_code,
            "command_summary": command_summary,
            "output": truncated_output,
            "output_truncated": was_truncated,
            "timed_out": False,
            "detached": False,
            "duration_ms": round((time.monotonic() - t0) * 1000, 2),
            "summary": {"errors": semantic_errors},
            "task_id": task_id,
        }

    # Standard synchronous execution path (preserves mock Popen & process group kill compatibility)
    timeout = float(timeout_seconds) if timeout_seconds is not None else float(_DEFAULT_TIMEOUT)
    timeout = min(timeout, float(_MAX_TIMEOUT))

    proc = subprocess.Popen(
        ["/bin/bash", "-lc", command],
        cwd=str(resolved_cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        text=True,
    )

    t0 = time.monotonic()
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_group(proc.pid)
        try:
            stdout, stderr = proc.communicate(timeout=2.0)
        except Exception:
            stdout, stderr = "", ""
        timed_out = True

    duration_ms = round((time.monotonic() - t0) * 1000, 2)
    raw_output = (stdout or "") + ("\n" + stderr if stderr else "")
    truncated_output, was_truncated = _truncate_output(raw_output)
    semantic_errors = _extract_semantic_errors(raw_output)
    exit_code = -9 if timed_out else (proc.returncode if proc.returncode is not None else 0)

    result = {
        "ok": (exit_code == 0) and not timed_out,
        "exit_code": exit_code,
        "command_summary": command_summary,
        "output": truncated_output,
        "output_truncated": was_truncated,
        "timed_out": timed_out,
        "duration_ms": duration_ms,
        "summary": {"errors": semantic_errors},
    }

    _record_tool_call("terminal_execute", validated)
    if isinstance(result, dict):
        result = enforce_payload(result)
    return result
