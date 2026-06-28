import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import MAX_OUTPUT_BYTES, RUNS_DIR
from app.file_package import check_total_size_and_validate, sha256_bytes, write_files
from app.idempotency import run_once, stable_key
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


def _normalize_file_payload(file_payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(file_payload)
    if "path" not in normalized and "name" in normalized:
        normalized["path"] = normalized.pop("name")
    return normalized


@mcp.tool(
    name="run_basic_python_solver",
    description=(
        "Run a lightweight Python pwn/web solver on this host in the MCP virtualenv. "
        "Use for basic CTF connectivity and solving without Docker. "
        "Installed packages include requests, beautifulsoup4, lxml, pwntools, pycryptodome, z3-solver, sympy, gmpy2, websocket-client, and websockets. "
        "Files may use either 'path' or 'name' for the file path. "
        "If target is provided, host:port must be allowlisted and TARGET_HOST/TARGET_PORT are passed to the solver."
    ),
)
def run_basic_python_solver(
    files: List[Dict[str, Any]],
    target: Optional[Dict[str, Any]] = None,
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

        dedupe_key = stable_key(
            "run_basic_python_solver",
            {
                "files": [_normalize_file_payload(f) for f in files],
                "target": target,
                "entrypoint": entrypoint,
                "args": args,
                "env": env,
                "timeout_seconds": timeout_seconds,
            },
        )
        return run_once(
            dedupe_key,
            ttl_seconds=max(30, min(int(timeout_seconds) + 15, 180)),
            fn=lambda: _run_basic_python_solver_once(files, target, entrypoint, args, env, timeout_seconds),
        )
    except Exception as e:
        log_audit_event("BASIC_RUN_ERROR", {"error": str(e)})
        return format_error_response(e)


def _run_basic_python_solver_once(
    files: List[Dict[str, Any]],
    target: Optional[Dict[str, Any]],
    entrypoint: str,
    args: List[str],
    env: Dict[str, str],
    timeout_seconds: int,
) -> Dict[str, Any]:
    try:

        validate_timeout(timeout_seconds)
        validate_args(args)
        validate_relative_path(entrypoint)

        target_host = None
        target_port = None
        warnings = []
        if target is not None:
            target_host = target.get("host")
            target_port = target.get("port")
            if not target_host or target_port is None:
                raise ValueError("target must include host and port when provided.")
            validate_target_allowlisted(str(target_host), int(target_port))
            block_private_or_local_host(str(target_host), int(target_port))
        else:
            warnings.append(
                "No target provided; TARGET_HOST/TARGET_PORT were not set. "
                "Provide target={host, port} for real pwn/web connections."
            )

        file_entries = [FileEntry(**_normalize_file_payload(f)) for f in files]
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
        if target_host is not None:
            child_env["TARGET_HOST"] = str(target_host)
            child_env["TARGET_PORT"] = str(target_port)

        bootstrap_code = (
            "import sys, os, runpy; "
            "sys.argv = sys.argv[1:]; "
            "curr = os.path.abspath(os.getcwd()); "
            "sys.path = [p for p in sys.path if p and os.path.abspath(p) != curr]; "
            "sys.path.append(curr); "
            "runpy.run_path(sys.argv[0], run_name='__main__')"
        )
        command = [sys.executable, "-c", bootstrap_code, entrypoint] + args
        log_audit_event(
            "BASIC_RUN_REQUEST",
            {
                "run_id": run_id,
                "entrypoint": entrypoint,
                "target": f"{target_host}:{target_port}" if target_host is not None else None,
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
        transcript = (
            f"run_id={run_id}\n"
            f"type=basic_python_solver\n"
            f"target={f'{target_host}:{target_port}' if target_host is not None else ''}\n"
            f"entrypoint={entrypoint}\n"
            f"exit_code={exit_code}\n"
            f"duration_ms={duration_ms}\n"
        )
        (output_dir / "transcript.txt").write_text(transcript, encoding="utf-8")
        transcript_sha256 = sha256_bytes(transcript.encode("utf-8"))

        metadata = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "type": "basic_python_solver",
            "target": f"{target_host}:{target_port}" if target_host is not None else None,
            "language": "python",
            "entrypoint": entrypoint,
            "timeout_seconds": timeout_seconds,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "files": [{"path": path, "size": len(content), "sha256": sha256_bytes(content)} for path, content in decoded_files],
            "stdout_sha256": stdout_sha256,
            "stderr_sha256": stderr_sha256,
            "transcript_sha256": transcript_sha256,
        }
        (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

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
            "transcript_sha256": transcript_sha256,
            "truncated": truncated,
            "warnings": warnings,
        }
    except Exception as e:
        log_audit_event("BASIC_RUN_ERROR", {"error": str(e)})
        return format_error_response(e)
