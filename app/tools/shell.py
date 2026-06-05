import uuid
import subprocess
from typing import Dict, Any
from app.mcp_server import mcp
from app.config import (
    WORKSPACES_DIR,
    DOCKER_MEMORY,
    DOCKER_CPUS,
    DOCKER_PIDS_LIMIT,
    MAX_OUTPUT_BYTES
)
from app.docker_runner import get_runner_image
from app.tools.workspace import validate_workspace_id_safe
from app.security import validate_language, validate_timeout, format_error_response
from app.logging_audit import log_audit_event


@mcp.tool(
    name="run_command",
    description=(
        "Run an arbitrary shell command inside an isolated Docker container. "
        "Use for forensics analysis, binary inspection, file extraction, etc. "
        "Requires an active workspace_id from create_workspace."
    )
)
def run_command(
    workspace_id: str,
    command: str,
    language: str = "forensics",
    timeout_seconds: int = 30
) -> Dict[str, Any]:
    """Runs a shell command inside an isolated container with volume mounting to the persistent workspace."""
    try:
        validate_workspace_id_safe(workspace_id)
        validate_language(language)
        validate_timeout(timeout_seconds)

        # Chặn các lệnh nguy hiểm
        BLOCKED = ["rm -rf /", "mkfs", "dd if=/dev/zero", "> /dev/sd"]
        if any(b in command for b in BLOCKED):
            raise ValueError(f"Blocked command pattern detected.")

        workspace_dir = WORKSPACES_DIR / workspace_id
        if not workspace_dir.exists():
            raise FileNotFoundError(f"Workspace '{workspace_id}' not found.")

        image = get_runner_image(language)
        container_name = f"shell_{workspace_id}_{uuid.uuid4().hex[:6]}"

        docker_cmd = [
            "docker", "run", "--rm",
            "--name", container_name,
            "--memory", DOCKER_MEMORY,
            "--cpus", str(DOCKER_CPUS),
            "--pids-limit", str(DOCKER_PIDS_LIMIT),
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--network", "none",  # no network cho shell commands
            "-v", f"{workspace_dir.resolve()}:/work:rw",
            "-w", "/work",
            "--entrypoint", "bash",
            image,
            "-c", command
        ]

        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            timeout=timeout_seconds
        )

        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")

        # Truncate
        if len(stdout) > MAX_OUTPUT_BYTES:
            stdout = stdout[:MAX_OUTPUT_BYTES] + "\n... [TRUNCATED]"

        log_audit_event("SHELL_COMMAND", {
            "workspace_id": workspace_id,
            "command": command,
            "exit_code": result.returncode
        })

        return {
            "ok": True,
            "workspace_id": workspace_id,
            "command": command,
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr
        }

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": {"code": "TIMEOUT", "message": f"Command timed out after {timeout_seconds}s"}}
    except Exception as e:
        return format_error_response(e)
