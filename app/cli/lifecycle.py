from __future__ import annotations

import os
import socket
import subprocess  # nosec B404
from pathlib import Path
from typing import Any, Sequence

from app.cli.config_view import bool_value, resolve_config_path
from app.cli.errors import CLIError, EXIT_OPERATION_FAILED


def read_pid(path: Path) -> int | None:
    try:
        value = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return value if value > 0 else None


def process_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def process_command_line(pid: int | None) -> str:
    if not process_running(pid):
        return ""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()


def process_matches(pid: int | None, kind: str) -> bool:
    command_line = process_command_line(pid)
    if not command_line:
        return False
    if kind in {"supervisor", "launcher"}:
        return "start_tunnel_server.sh" in command_line
    if kind == "server":
        return "fastmcp" in command_line and "app/main.py" in command_line
    if kind == "tunnel":
        return all(fragment in command_line for fragment in ("cloudflared", "tunnel", "--url"))
    return False


def canonical_tunnel_base(repo_root: Path) -> str | None:
    path = repo_root / "logs" / "tunnel_url.txt"
    try:
        value = path.read_text(encoding="utf-8").splitlines()[0].strip().rstrip("/")
    except (OSError, IndexError):
        return None
    if not value.startswith("https://") or ".trycloudflare.com" not in value:
        return None
    return value


def connector_url(repo_root: Path, values: dict[str, str]) -> str | None:
    base = canonical_tunnel_base(repo_root)
    if not base:
        return None
    path = values.get("MCP_PATH", "/mcp").strip() or "/mcp"
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def bridge_ready(values: dict[str, str], timeout: float = 0.25) -> bool:
    host = values.get("MCP_CONNECT_HOST", "127.0.0.1").strip() or "127.0.0.1"
    if host in {"0.0.0.0", "::"}:  # nosec B104
        host = "127.0.0.1"
    try:
        port = int(values.get("MCP_PORT", "8000"))
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def status_data(repo_root: Path, values: dict[str, str]) -> dict[str, Any]:
    logs = repo_root / "logs"
    watchdog_pid = read_pid(logs / "watchdog.pid")
    launcher_pid = read_pid(logs / "launcher.pid")
    supervisor_pid = (
        watchdog_pid
        if process_matches(watchdog_pid, "supervisor")
        else launcher_pid
        if process_matches(launcher_pid, "launcher")
        else None
    )
    server_pid = read_pid(logs / "server.pid")
    tunnel_pid = read_pid(logs / "tunnel.pid")
    server_running = process_matches(server_pid, "server")
    tunnel_running = process_matches(tunnel_pid, "tunnel")
    url = connector_url(repo_root, values) if tunnel_running else None
    bridge = "ready" if server_running and bridge_ready(values) else "starting" if server_running else "stopped"
    workspace = resolve_config_path(
        repo_root, values.get("HOST_WORKSPACE_DIR", str(Path.home()))
    )
    return {
        "ok": bool(server_running and tunnel_running and bridge == "ready"),
        "supervisor": {"running": bool(supervisor_pid), "pid": supervisor_pid},
        "server": {"running": server_running, "pid": server_pid},
        "tunnel": {"running": tunnel_running, "pid": tunnel_pid},
        "bridge": bridge,
        "url": url,
        "auth_required": bool_value(values, "REQUIRE_AUTH", True),
        "workspace": str(workspace),
    }


def run_script(
    repo_root: Path,
    relative_path: str,
    arguments: Sequence[str] = (),
    *,
    timeout: float = 120.0,
) -> dict[str, Any]:
    script = repo_root / relative_path
    if not script.is_file():
        raise CLIError(f"Lifecycle script not found: {script}")
    try:
        process = subprocess.run(  # nosec B603
            [str(script), *arguments],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CLIError(
            f"Lifecycle command timed out after {timeout:g}s: {relative_path}",
            EXIT_OPERATION_FAILED,
        ) from exc
    result = {
        "ok": process.returncode == 0,
        "script": relative_path,
        "arguments": list(arguments),
        "exit_code": process.returncode,
        "stdout": process.stdout,
        "stderr": process.stderr,
    }
    if process.returncode != 0:
        detail = process.stderr.strip() or process.stdout.strip() or f"exit code {process.returncode}"
        raise CLIError(f"Lifecycle command failed: {detail}", details=result)
    return result


def start(repo_root: Path) -> dict[str, Any]:
    return run_script(repo_root, "run_mcp_tunnel.sh", ["start"])


def stop(repo_root: Path) -> dict[str, Any]:
    return run_script(repo_root, "run_mcp_tunnel.sh", ["stop"])


def restart(repo_root: Path) -> dict[str, Any]:
    return run_script(repo_root, "run_mcp_tunnel.sh", ["restart"], timeout=180.0)


def server_restart(repo_root: Path, values: dict[str, str]) -> dict[str, Any]:
    before = status_data(repo_root, values)
    result = run_script(repo_root, "scripts/restart_server_only.sh", timeout=120.0)
    after = status_data(repo_root, values)
    tunnel_preserved = (
        before["tunnel"]["pid"] == after["tunnel"]["pid"]
        and before.get("url") == after.get("url")
    )
    return {
        "ok": bool(result["ok"] and after["server"]["running"] and after["bridge"] == "ready" and tunnel_preserved),
        "operation": "server_restart",
        "tunnel_preserved": tunnel_preserved,
        "before": before,
        "after": after,
        "stdout": result["stdout"],
        "stderr": result["stderr"],
    }
