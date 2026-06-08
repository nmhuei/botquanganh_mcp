import uuid
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from app.mcp_server import mcp
import app.config
from app.docker_runner import get_runner_image
from app.tools.workspace import ensure_workspace_tools_enabled, validate_workspace_id_safe
from app.security import validate_language, validate_timeout, format_error_response
from app.logging_audit import log_audit_event


SAFE_COMMAND_PREFIXES = {
    # Navigation / basic utilities
    "cd", "ls", "pwd", "cat", "echo", "clear", "grep", "rg", "find", "head", "tail", "less", "mkdir", "cp", "mv", "rm", "tar", "unzip", "zip",
    # PWN
    "file", "strings", "readelf", "objdump", "checksec", "ROPgadget", "ropper", "gdb", "python3", "python", "pwndbg",
    # Crypto
    "sage", "openssl", "z3", "RsaCtfTool",
    # Forensics
    "exiftool", "binwalk", "foremost", "xxd", "tshark", "volatility3", "zsteg",
    # Web
    "curl", "wget", "ffuf", "nmap"
}

def _is_nmap_safe(parts: list) -> bool:
    """Checks if nmap is run with safe flags. Denies aggressive/script flags."""
    for part in parts[1:]:
        if part.startswith("-"):
            allowed = False
            for safe_flag in ["-p", "-sV", "-sC", "-F", "-T", "-v", "--open", "-A", "-Pn"]:
                if part.startswith(safe_flag):
                    allowed = True
                    break
            # Explicitly block unsafe options
            if part in ("-p-", "--script") or part.startswith("--script="):
                allowed = False
            if not allowed:
                return False
    return True

def _inspect_command_policy(command: str) -> Optional[Dict[str, str]]:
    if not command or not command.strip():
        raise ValueError("Command must not be empty.")

    # Critical forbidden patterns (never allowed)
    forbidden_patterns = [
        ("destructive_rm_root", "rm -rf /", "Use write_file/replace_in_file/delete tools instead of destructive shell removal."),
        ("destructive_rm_glob_root", "rm -rf /*", "Use scoped file-management tools instead of deleting from root."),
        ("filesystem_format", "mkfs", "Formatting disks is blocked in MCP shell mode."),
        ("disk_zeroing", "dd if=/dev/zero", "Raw disk writes are blocked in MCP shell mode."),
        ("raw_block_device_write", "> /dev/sd", "Direct block-device writes are blocked in MCP shell mode."),
        ("fork_bomb", ":(){", "Process-fork bombs are blocked in MCP shell mode."),
        ("shutdown_host", "shutdown", "Host shutdown is blocked in MCP shell mode."),
        ("reboot_host", "reboot", "Host reboot is blocked in MCP shell mode."),
        ("poweroff_host", "poweroff", "Host poweroff is blocked in MCP shell mode."),
    ]
    command_lower = command.lower()
    for rule_name, fragment, suggested_alternative in forbidden_patterns:
        if fragment in command_lower:
            return {
                "blocked_command_rule": rule_name,
                "matched_fragment": fragment,
                "suggested_alternative": suggested_alternative,
                "severity": "forbidden"
            }

    # Allowlist parsing: Split by command chain operators
    import re
    # Split by ;, &&, ||, |
    parts = re.split(r';|&&|\|\||\|', command)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        words = part.split()
        if not words:
            continue
        
        # Clean variable assignments/env prefixes (e.g. PORT=8000 python3)
        word_idx = 0
        while word_idx < len(words) and "=" in words[word_idx]:
            word_idx += 1
        if word_idx >= len(words):
            continue
        first_word = words[word_idx]

        if first_word not in SAFE_COMMAND_PREFIXES:
            return {
                "blocked_command_rule": "unknown_command_allowlist_violation",
                "matched_fragment": first_word,
                "suggested_alternative": f"Command '{first_word}' is not in the safe allowlist. Requires explicit approval.",
                "severity": "needs_approval"
            }

        if first_word == "nmap":
            if not _is_nmap_safe(words[word_idx:]):
                return {
                    "blocked_command_rule": "nmap_aggressive_scan_violation",
                    "matched_fragment": part,
                    "suggested_alternative": "nmap scan uses aggressive or unsafe flags. Requires explicit approval.",
                    "severity": "needs_approval"
                }

    return None


def _validate_command_safe_enough(command: str, approval: str = "auto_safe") -> None:
    blocked = _inspect_command_policy(command)
    if blocked:
        if blocked.get("severity") == "forbidden":
            raise PermissionError(
                f"Command is strictly forbidden: blocked_command_rule={blocked['blocked_command_rule']}; "
                f"matched_fragment={blocked['matched_fragment']}; "
                f"suggested_alternative={blocked['suggested_alternative']}"
            )
        if blocked.get("severity") == "needs_approval" and approval != "approved":
            raise PermissionError(
                f"Command requires explicit approval: blocked_command_rule={blocked['blocked_command_rule']}; "
                f"matched_fragment={blocked['matched_fragment']}; "
                f"suggested_alternative={blocked['suggested_alternative']}"
            )


def _resolve_host_cwd(cwd: Optional[str]) -> Path:
    base_dir = app.config.AGENT_WORKSPACE_DIR.resolve()
    resolved = (Path(cwd).expanduser() if cwd else base_dir)
    if not resolved.is_absolute():
        resolved = base_dir / resolved
    resolved = resolved.resolve()

    if app.config.AGENT_RESTRICT_TO_WORKSPACE:
        try:
            resolved.relative_to(base_dir)
        except ValueError:
            raise PermissionError(
                f"Access denied. cwd '{cwd}' is outside the agent workspace directory '{base_dir}'."
            )

    if not resolved.exists() or not resolved.is_dir():
        raise FileNotFoundError(f"Working directory not found: {resolved}")
    return resolved


@mcp.tool(
    name="policy_check_command",
    description=(
        "Dry-run policy inspection for a host shell command and optional cwd. "
        "Returns whether the command would be allowed, plus the specific blocking rule when denied."
    )
)
def policy_check_command(command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
    try:
        blocked = _inspect_command_policy(command)
        if blocked:
            return {
                "ok": True,
                "allowed": False,
                "mode": "host",
                "blocked_reason": blocked["blocked_command_rule"],
                "matched_fragment": blocked["matched_fragment"],
                "suggested_alternative": blocked["suggested_alternative"],
                "severity": blocked.get("severity", "forbidden"),
            }

        resolved_cwd = _resolve_host_cwd(cwd)
        return {
            "ok": True,
            "allowed": True,
            "mode": "host",
            "cwd": str(resolved_cwd),
        }
    except Exception as e:
        return format_error_response(e)


def _truncate_output(stdout: str, stderr: str) -> Tuple[str, str]:
    if len(stdout) > app.config.MAX_OUTPUT_BYTES:
        stdout = stdout[:app.config.MAX_OUTPUT_BYTES] + "\n... [TRUNCATED]"
    if len(stderr) > app.config.MAX_OUTPUT_BYTES:
        stderr = stderr[:app.config.MAX_OUTPUT_BYTES] + "\n... [TRUNCATED]"
    return stdout, stderr


def _run_host_command_impl(command: str, timeout_seconds: int, cwd: Optional[str]) -> Dict[str, Any]:
    workspace_dir = _resolve_host_cwd(cwd)
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=workspace_dir.resolve(),
        capture_output=True,
        timeout=timeout_seconds
    )

    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    stdout, stderr = _truncate_output(stdout, stderr)

    log_audit_event("SHELL_COMMAND", {
        "workspace_id": "",
        "command": command,
        "cwd": str(workspace_dir.resolve()),
        "mode": "host",
        "exit_code": result.returncode
    })

    return {
        "ok": True,
        "workspace_id": "",
        "command": command,
        "cwd": str(workspace_dir.resolve()),
        "mode": "host",
        "exit_code": result.returncode,
        "stdout": stdout,
        "stderr": stderr
    }


def _run_workspace_command_impl(
    command: str,
    workspace_id: str,
    language: str,
    timeout_seconds: int,
) -> Dict[str, Any]:
    ensure_workspace_tools_enabled()
    validate_workspace_id_safe(workspace_id)
    workspace_dir = app.config.WORKSPACES_DIR / workspace_id
    if not workspace_dir.exists():
        raise FileNotFoundError(f"Workspace '{workspace_id}' not found.")

    run_mode = "host"
    if app.config.USE_DOCKER and language not in ("host", "local"):
        validate_language(language)
        run_mode = "docker"
        image = get_runner_image(language)
        container_name = f"shell_{workspace_id}_{uuid.uuid4().hex[:6]}"

        exec_cmd = [
            "docker", "run", "--rm",
            "--name", container_name,
            "--memory", app.config.DOCKER_MEMORY,
            "--cpus", str(app.config.DOCKER_CPUS),
            "--pids-limit", str(app.config.DOCKER_PIDS_LIMIT),
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--network", "none",
            "-v", f"{workspace_dir.resolve()}:/work:rw",
            "-w", "/work",
            "--entrypoint", "bash",
            image,
            "-c", command
        ]
        result = subprocess.run(
            exec_cmd,
            capture_output=True,
            timeout=timeout_seconds
        )
    else:
        result = subprocess.run(
            ["bash", "-c", command],
            cwd=workspace_dir.resolve(),
            capture_output=True,
            timeout=timeout_seconds
        )

    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    stdout, stderr = _truncate_output(stdout, stderr)

    log_audit_event("SHELL_COMMAND", {
        "workspace_id": workspace_id,
        "command": command,
        "cwd": str(workspace_dir.resolve()),
        "mode": run_mode,
        "exit_code": result.returncode
    })

    response: Dict[str, Any] = {
        "ok": True,
        "workspace_id": workspace_id,
        "command": command,
        "cwd": str(workspace_dir.resolve()),
        "mode": run_mode,
        "exit_code": result.returncode,
        "stdout": stdout,
        "stderr": stderr
    }
    if language == "host":
        response["warnings"] = [
            "workspace_id + language=host runs on the host against the workspace directory.",
            "Prefer run_host_command for host work outside a managed workspace."
        ]
    return response


@mcp.tool(
    name="run_host_command",
    description=(
        "Run a shell command directly on the host machine inside the configured agent workspace. "
        "Use this instead of run_command when you do not need a managed workspace_id."
    )
)
def run_host_command(command: str, timeout_seconds: int = 30, cwd: Optional[str] = None, approval: str = "auto_safe") -> Dict[str, Any]:
    try:
        validate_timeout(timeout_seconds)
        _validate_command_safe_enough(command, approval)
        return _run_host_command_impl(command, timeout_seconds, cwd)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": {"code": "TIMEOUT", "message": f"Command timed out after {timeout_seconds}s"}}
    except Exception as e:
        return format_error_response(e)


@mcp.tool(
    name="run_workspace_command",
    description=(
        "Run a shell command against a managed workspace_id. "
        "Use language=python/pwn/sage/forensics for Docker execution, or language=host for host-side execution limited to that workspace."
    )
)
def run_workspace_command(
    workspace_id: str,
    command: str,
    language: str = "forensics",
    timeout_seconds: int = 30,
    approval: str = "auto_safe",
) -> Dict[str, Any]:
    try:
        validate_timeout(timeout_seconds)
        _validate_command_safe_enough(command, approval)
        return _run_workspace_command_impl(command, workspace_id, language, timeout_seconds)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": {"code": "TIMEOUT", "message": f"Command timed out after {timeout_seconds}s"}}
    except Exception as e:
        return format_error_response(e)


@mcp.tool(
    name="run_command",
    description=(
        "Run a shell command. Without workspace_id, runs on the host inside the configured "
        "agent workspace. With workspace_id, runs inside the isolated Docker workspace flow. "
        "Useful for normal commands like pwd, ls, cat, find, rg, python, bash, curl, wget, "
        "nc, ncat, nmap, jq, openssl, dig, and host."
    )
)
def run_command(
    command: str,
    workspace_id: str = "",
    language: str = "host",
    timeout_seconds: int = 30,
    cwd: Optional[str] = None,
    approval: str = "auto_safe",
) -> Dict[str, Any]:
    """Runs a shell command on the host workspace or inside an isolated workspace container."""
    try:
        validate_timeout(timeout_seconds)
        _validate_command_safe_enough(command, approval)
        if workspace_id:
            return _run_workspace_command_impl(command, workspace_id, language, timeout_seconds)

        response = _run_host_command_impl(command, timeout_seconds, cwd)
        response["warnings"] = [
            "run_command without workspace_id uses host mode for backward compatibility.",
            "Prefer run_host_command for explicit host execution."
        ]
        return response

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": {"code": "TIMEOUT", "message": f"Command timed out after {timeout_seconds}s"}}
    except Exception as e:
        return format_error_response(e)
