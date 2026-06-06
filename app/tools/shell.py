import uuid
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from app.mcp_server import mcp
import app.config
from app.docker_runner import get_runner_image
from app.tools.workspace import validate_workspace_id_safe
from app.security import validate_language, validate_timeout, format_error_response
from app.logging_audit import log_audit_event


def _validate_command_safe_enough(command: str) -> None:
    if not command or not command.strip():
        raise ValueError("Command must not be empty.")

    blocked_patterns = [
        "rm -rf /",
        "rm -rf /*",
        "mkfs",
        "dd if=/dev/zero",
        "> /dev/sd",
        ":(){",
        "shutdown",
        "reboot",
        "poweroff",
    ]
    command_lower = command.lower()
    if any(pattern in command_lower for pattern in blocked_patterns):
        raise ValueError("Blocked command pattern detected.")


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
) -> Dict[str, Any]:
    """Runs a shell command on the host workspace or inside an isolated workspace container."""
    try:
        validate_timeout(timeout_seconds)
        _validate_command_safe_enough(command)

        run_mode = "host"
        workspace_dir: Path

        if workspace_id:
            validate_workspace_id_safe(workspace_id)
            workspace_dir = app.config.WORKSPACES_DIR / workspace_id
            if not workspace_dir.exists():
                raise FileNotFoundError(f"Workspace '{workspace_id}' not found.")
        else:
            workspace_dir = _resolve_host_cwd(cwd)

        if workspace_id and app.config.USE_DOCKER and language not in ("host", "local"):
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
                "--network", "none",  # no network for shell commands
                "-v", f"{workspace_dir.resolve()}:/work:rw",
                "-w", "/work",
                "--entrypoint", "bash",
                image,
                "-c", command
            ]
        else:
            exec_cmd = ["bash", "-c", command]

        result = subprocess.run(
            exec_cmd,
            cwd=workspace_dir.resolve() if run_mode == "host" else None,
            capture_output=True,
            timeout=timeout_seconds
        )

        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")

        # Truncate
        if len(stdout) > app.config.MAX_OUTPUT_BYTES:
            stdout = stdout[:app.config.MAX_OUTPUT_BYTES] + "\n... [TRUNCATED]"
        if len(stderr) > app.config.MAX_OUTPUT_BYTES:
            stderr = stderr[:app.config.MAX_OUTPUT_BYTES] + "\n... [TRUNCATED]"

        log_audit_event("SHELL_COMMAND", {
            "workspace_id": workspace_id,
            "command": command,
            "cwd": str(workspace_dir.resolve()),
            "mode": run_mode,
            "exit_code": result.returncode
        })

        return {
            "ok": True,
            "workspace_id": workspace_id,
            "command": command,
            "cwd": str(workspace_dir.resolve()),
            "mode": run_mode,
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr
        }

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": {"code": "TIMEOUT", "message": f"Command timed out after {timeout_seconds}s"}}
    except Exception as e:
        return format_error_response(e)
