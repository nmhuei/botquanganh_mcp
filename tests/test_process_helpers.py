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


def test_quick_tunnel_parser_only_reads_current_launch_bytes(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    log = tmp_path / "cloudflared.log"
    old = "INF https://old.trycloudflare.com\n"
    log.write_text(old, encoding="utf-8")
    offset = log.stat().st_size
    with log.open("a", encoding="utf-8") as handle:
        handle.write("INF https://new.trycloudflare.com\n")
        handle.write("INF Registered tunnel connection connIndex=0\n")
    command = f"""
source {repo_root / 'scripts/process_helpers.sh'}
quick_tunnel_url_from_log_since {log} {offset}
cloudflared_registered_since {log} {offset}
"""
    result = subprocess.run(["bash", "-c", command], capture_output=True, text=True)
    assert result.returncode == 0
    assert result.stdout.strip() == "https://new.trycloudflare.com"


def test_supervisor_has_process_identity_startup_grace():
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "scripts/start_tunnel_server.sh").read_text(encoding="utf-8")
    assert 'pid_is_alive "$server_pid"' in source
    assert 'now - SERVER_STARTED_AT' in source


def test_supervisor_restores_missing_runtime_pid_files_and_tracks_children():
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "scripts/start_tunnel_server.sh").read_text(encoding="utf-8")
    assert 'MANAGED_SERVER_PID=""' in source
    assert 'MANAGED_TUNNEL_PID=""' in source
    assert 'atomic_write "$SERVER_PID_FILE" "$MANAGED_SERVER_PID"' in source
    assert 'atomic_write "$TUNNEL_PID_FILE" "$MANAGED_TUNNEL_PID"' in source
    assert 'stop_managed_pid "$MANAGED_SERVER_PID" server "MCP Server"' in source
    assert 'stop_managed_pid "$MANAGED_TUNNEL_PID" tunnel "Cloudflare Tunnel"' in source


def test_server_restart_requires_the_replacement_to_own_the_listener():
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "scripts/restart_server_only.sh").read_text(encoding="utf-8")
    assert 'listening_pids_on_port "$MCP_PORT"' in source
    assert 'atomic_write_runtime_file "$PID_FILE" "$listener_pid"' in source
    assert 'healthz_ready' in source


def test_launcher_accepts_adopted_active_connector_without_waiting_for_new_url():
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "run_mcp_tunnel.sh").read_text(encoding="utf-8")
    assert 'previous_active_url=$(active_connector_url || true)' in source
    assert '[ -n "$previous_active_url" ] || [ -z "$previous_url" ] || [ "$url" != "$previous_url" ]' in source


def test_tunnel_start_creates_log_before_reading_launch_offset():
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "scripts/start_tunnel_server.sh").read_text(encoding="utf-8")
    touch_index = source.index('touch "$CLOUDFLARED_LOG"')
    offset_index = source.index('TUNNEL_LOG_OFFSET=$(wc -c < "$CLOUDFLARED_LOG")')
    assert touch_index < offset_index
