import subprocess
import sys
from pathlib import Path


def _helper_command(repo_root: Path, body: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f"source scripts/process_helpers.sh\n{body}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_process_helper_refuses_unrelated_live_pid(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    process = subprocess.Popen(["sleep", "30"])
    try:
        pid_file = tmp_path / "server.pid"
        pid_file.write_text(str(process.pid), encoding="utf-8")
        result = _helper_command(
            repo_root,
            f'stop_managed_pid_file "{pid_file}" server "MCP Server"',
        )
        assert result.returncode == 0
        assert process.poll() is None
        assert not pid_file.exists()
        assert "Refusing to stop unrelated process" in result.stderr
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_process_helper_stops_matching_managed_pid(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    process = subprocess.Popen(
        ["bash", "-c", "exec -a 'cloudflared tunnel --url http://127.0.0.1:9' sleep 30"]
    )
    try:
        pid_file = tmp_path / "tunnel.pid"
        pid_file.write_text(str(process.pid), encoding="utf-8")
        result = _helper_command(
            repo_root,
            f'stop_managed_pid_file "{pid_file}" tunnel "Cloudflare Tunnel"',
        )
        assert result.returncode == 0
        process.wait(timeout=5)
        assert not pid_file.exists()
        assert "Stopping Cloudflare Tunnel" in result.stdout
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def test_cli_process_matching_rejects_unrelated_pid():
    import app.cli.lifecycle as lifecycle

    process = subprocess.Popen(["sleep", "30"])
    try:
        assert lifecycle.process_running(process.pid) is True
        assert lifecycle.process_matches(process.pid, "server") is False
        assert lifecycle.process_matches(process.pid, "tunnel") is False
        assert lifecycle.process_matches(process.pid, "supervisor") is False
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_listening_pid_filter_excludes_connected_client():
    repo_root = Path(__file__).resolve().parents[1]
    server_code = (
        "import socket,time\n"
        "sock=socket.socket()\n"
        "sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)\n"
        "sock.bind(('127.0.0.1',0))\n"
        "sock.listen()\n"
        "print(sock.getsockname()[1], flush=True)\n"
        "conn,_=sock.accept()\n"
        "time.sleep(30)\n"
    )
    server = subprocess.Popen(
        [sys.executable, "-u", "-c", server_code],
        stdout=subprocess.PIPE,
        text=True,
    )
    client = None
    try:
        assert server.stdout is not None
        port = int(server.stdout.readline().strip())
        client_code = (
            "import socket,sys,time\n"
            "sock=socket.create_connection(('127.0.0.1',int(sys.argv[1])))\n"
            "print('connected', flush=True)\n"
            "time.sleep(30)\n"
        )
        client = subprocess.Popen(
            [sys.executable, "-u", "-c", client_code, str(port)],
            stdout=subprocess.PIPE,
            text=True,
        )
        assert client.stdout is not None
        assert client.stdout.readline().strip() == "connected"

        result = _helper_command(repo_root, f"listening_pids_on_port {port}")
        assert result.returncode == 0
        pids = {int(line) for line in result.stdout.splitlines() if line.strip()}
        assert server.pid in pids
        assert client.pid not in pids
    finally:
        if client is not None and client.poll() is None:
            client.terminate()
            client.wait(timeout=5)
        if server.poll() is None:
            server.terminate()
            server.wait(timeout=5)
