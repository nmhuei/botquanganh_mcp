"""Regressions for two checkouts accidentally sharing one MCP port."""

import os
import shlex
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

import app.cli.lifecycle as lifecycle


ROOT = Path(__file__).resolve().parents[1]


def test_status_does_not_accept_another_process_listener(monkeypatch, tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "server.pid").write_text(str(os.getpid()))
    (logs / "tunnel.pid").write_text(str(os.getpid()))
    (logs / "tunnel_url.txt").write_text("https://example.trycloudflare.com")
    # External process identity is controlled; socket ownership is real.
    monkeypatch.setattr(lifecycle, "process_matches", lambda pid, kind, *args: bool(pid))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        code = "import socket,sys,time; s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(); print(s.getsockname()[1],flush=True); time.sleep(30)"
        other = subprocess.Popen([sys.executable, "-u", "-c", code], stdout=subprocess.PIPE, text=True)
        try:
            other_port = int(other.stdout.readline())
            values = {"MCP_PORT": str(other_port), "HOST_WORKSPACE_DIR": str(tmp_path)}
            status = lifecycle.status_data(tmp_path, values)
            assert status["connector_ready"] is False
            assert status["bridge"] != "ready"
            # A matching PID with its own listener must still become ready.
            values["MCP_PORT"] = str(port)
            assert lifecycle.status_data(tmp_path, values)["connector_ready"] is True
        finally:
            other.terminate()
            other.wait(timeout=5)


def test_process_matches_rejects_server_from_another_checkout(monkeypatch, tmp_path):
    monkeypatch.setattr(lifecycle, "process_command_line", lambda pid: "fastmcp run app/main.py")
    assert lifecycle.process_matches(os.getpid(), "server", Path.cwd()) is True
    assert lifecycle.process_matches(os.getpid(), "server", tmp_path) is False


def test_shell_ownership_rejects_another_checkout(tmp_path):
    # Only the command-line reader is substituted; cwd ownership uses /proc.
    command = f"""
source {shlex.quote(str(ROOT / 'scripts/process_helpers.sh'))}
ROOT_DIR={shlex.quote(str(tmp_path))}
pid_command_line() {{ printf '%s' 'fastmcp run app/main.py'; }}
pid_matches_kind {os.getpid()} server
"""
    result = subprocess.run(["bash", "-c", command], capture_output=True, text=True)
    assert result.returncode == 1


def test_port_guard_refuses_foreign_listener_and_accepts_free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        command = f"source {shlex.quote(str(ROOT / 'scripts/process_helpers.sh'))}\nensure_server_port_available {port}\n"
        result = subprocess.run(["bash", "-c", command], capture_output=True, text=True)
        assert result.returncode == 1
        assert "occupied" in result.stderr
        assert listener.getsockname()[1] == port
    result = subprocess.run(["bash", "-c", command], capture_output=True, text=True)
    assert result.returncode == 0


@pytest.mark.parametrize("entrypoint", ["run_mcp_tunnel.sh", "scripts/start_tunnel_server.sh", "scripts/restart_server_only.sh"])
def test_lifecycle_refuses_foreign_checkout_without_touching_it(tmp_path, entrypoint):
    staged = tmp_path / "runtime"
    (staged / "scripts").mkdir(parents=True)
    (staged / ".venv/bin").mkdir(parents=True)
    for relative in ("run_mcp_tunnel.sh", "scripts/process_helpers.sh", "scripts/start_tunnel_server.sh", "scripts/restart_server_only.sh"):
        shutil.copy2(ROOT / relative, staged / relative)
    # These launchers must never run when another checkout already owns the port.
    for name in ("fastmcp", "cloudflared"):
        script = staged / ".venv/bin" / name
        script.write_text("#!/bin/sh\ntouch unexpected-spawn\nexit 1\n")
        script.chmod(0o755)
    code = "import socket,time; s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(); print(s.getsockname()[1],flush=True); time.sleep(30)"
    other = subprocess.Popen([sys.executable, "-u", "-c", code, "fastmcp", "app/main.py"], cwd=tmp_path, stdout=subprocess.PIPE, text=True)
    try:
        port = int(other.stdout.readline())
        env = dict(os.environ, MCP_PORT=str(port), PATH=f"{staged / '.venv/bin'}:{os.environ['PATH']}")
        result = subprocess.run(["bash", str(staged / entrypoint)], cwd=staged, env=env, capture_output=True, text=True, timeout=5)
        assert result.returncode == 1
        assert "occupied" in result.stderr
        assert other.poll() is None
        assert not (staged / "unexpected-spawn").exists()
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass
    finally:
        other.terminate()
        other.wait(timeout=5)
