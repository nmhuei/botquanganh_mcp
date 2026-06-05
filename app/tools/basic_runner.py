import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import MAX_OUTPUT_BYTES, RUNS_DIR
from app.file_package import check_total_size_and_validate, sha256_bytes, write_files
from app.logging_audit import log_audit_event
from app.mcp_server import mcp
from app.schemas import FileEntry
from app.security import (
    block_private_or_local_host,
    format_error_response,
    validate_args,
    validate_relative_path,
    validate_target_allowlisted,
    validate_timeout,
)


def _basic_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"basic_{stamp}_{os.urandom(4).hex()}"


@mcp.tool(
    name="run_basic_python_solver",
    description=(
        "Run a lightweight Python pwn/web solver on this host in the MCP virtualenv. "
        "Use for basic CTF connectivity and solving without Docker. "
        "Installed packages include requests, beautifulsoup4, lxml, pwntools, pycryptodome, z3-solver, sympy, gmpy2, websocket-client, and websockets. "
        "If target is provided, host:port must be allowlisted."
    ),
)
def run_basic_python_solver(
    files: List[Dict[str, Any]],
    target: Dict[str, Any],
    entrypoint: str = "solve.py",
    args: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
    timeout_seconds: int = 30,
) -> Dict[str, Any]:
    """Runs a Python solver directly in the MCP server virtualenv.

    This is the basic, no-Docker execution path. It is intentionally limited to
    Python, file-size checks, relative paths, allowlisted targets, and timeout.
    """
    try:
        if args is None:
            args = []
        if env is None:
            env = {}

        validate_timeout(timeout_seconds)
        validate_args(args)
        validate_relative_path(entrypoint)

        target_host = target.get("host")
        target_port = target.get("port")
        if not target_host or target_port is None:
            raise ValueError("target must include host and port.")
        validate_target_allowlisted(str(target_host), int(target_port))
        block_private_or_local_host(str(target_host), int(target_port))

        file_entries = [FileEntry(**f) for f in files]
        decoded_files = check_total_size_and_validate(file_entries)
        if not any(path == entrypoint for path, _ in decoded_files):
            raise ValueError(f"Entrypoint file '{entrypoint}' is missing from files.")

        run_id = _basic_run_id()
        run_dir = RUNS_DIR / run_id
        input_dir = run_dir / "input"
        output_dir = run_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        write_files(input_dir, decoded_files)

        child_env = os.environ.copy()
        child_env.update({str(k): str(v) for k, v in env.items()})
        child_env["TARGET_HOST"] = str(target_host)
        child_env["TARGET_PORT"] = str(target_port)

        command = [sys.executable, entrypoint] + args
        log_audit_event(
            "BASIC_RUN_REQUEST",
            {
                "run_id": run_id,
                "entrypoint": entrypoint,
                "target": f"{target_host}:{target_port}",
                "timeout_seconds": timeout_seconds,
            },
        )

        start = time.time()
        timed_out = False
        try:
            result = subprocess.run(
                command,
                cwd=input_dir,
                env=child_env,
                capture_output=True,
                timeout=timeout_seconds,
                text=False,
            )
            exit_code = result.returncode
            stdout_bytes = result.stdout or b""
            stderr_bytes = result.stderr or b""
        except subprocess.TimeoutExpired as e:
            timed_out = True
            exit_code = -1
            stdout_bytes = e.stdout or b""
            stderr_bytes = e.stderr or b""

        duration_ms = int((time.time() - start) * 1000)
        stdout_sha256 = sha256_bytes(stdout_bytes)
        stderr_sha256 = sha256_bytes(stderr_bytes)

        truncated = False
        if len(stdout_bytes) > MAX_OUTPUT_BYTES:
            stdout_bytes = stdout_bytes[:MAX_OUTPUT_BYTES] + b"\n... [TRUNCATED]"
            truncated = True
        if len(stderr_bytes) > MAX_OUTPUT_BYTES:
            stderr_bytes = stderr_bytes[:MAX_OUTPUT_BYTES] + b"\n... [TRUNCATED]"
            truncated = True

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        (output_dir / "stdout.txt").write_text(stdout, encoding="utf-8")
        (output_dir / "stderr.txt").write_text(stderr, encoding="utf-8")

        log_audit_event(
            "BASIC_RUN_COMPLETE",
            {
                "run_id": run_id,
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "timed_out": timed_out,
            },
        )

        return {
            "ok": not timed_out,
            "run_id": run_id,
            "entrypoint": entrypoint,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "duration_ms": duration_ms,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_sha256": stdout_sha256,
            "stderr_sha256": stderr_sha256,
            "truncated": truncated,
        }
    except Exception as e:
        log_audit_event("BASIC_RUN_ERROR", {"error": str(e)})
        return format_error_response(e)
