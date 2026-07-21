import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.cli.main import main


class CLIHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return

    def _json(self, status, payload):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/api/v1/health":
            self._json(
                200,
                {
                    "ok": True,
                    "service": "test-host",
                    "version": "1.0.0",
                    "profile": "host",
                    "workspace": "/tmp",
                    "command_policy": "guarded",
                    "metrics": {"uptime_seconds": 61, "total_requests": 2, "error_count": 0, "rate_limit_hits": 0, "avg_latency_ms": 1.2},
                },
            )
        elif self.path.startswith("/api/v1/files/content"):
            self._json(200, {"ok": True, "path": "note.txt", "content": "hello\n", "truncated": False})
        else:
            self._json(404, {"error": {"message": "missing"}})

    def do_POST(self):
        if self.path == "/api/v1/commands/run":
            self._json(500, {"ok": False, "exit_code": 7, "stdout": "", "stderr": "bad\n"})
        elif self.path == "/api/v1/commands/check":
            self._json(200, {"ok": True, "allowed": True, "policy": "guarded", "command_names": ["printf"], "severity": "none", "rule": None})
        else:
            self._json(404, {"error": {"message": "missing"}})


@pytest.fixture
def cli_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), CLIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_health_json_integration(cli_server, capsys):
    assert main(["health", "--base-url", cli_server, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["service"] == "test-host"


def test_fs_cat_human_integration(cli_server, capsys):
    assert main(["--base-url", cli_server, "fs", "cat", "note.txt"]) == 0
    assert capsys.readouterr().out == "hello\n"


def test_command_nonzero_exit_is_preserved(cli_server, capsys):
    assert main(["cmd", "run", "false", "--base-url", cli_server]) == 7
    captured = capsys.readouterr()
    assert captured.err == "bad\n"


def test_command_policy_check(cli_server, capsys):
    assert main(["cmd", "check", "printf ok", "--base-url", cli_server, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["allowed"] is True


def test_full_restart_requires_yes_when_noninteractive(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert main(["restart"]) == 2
    assert "requires --yes" in capsys.readouterr().err


def test_completion_generation(capsys):
    assert main(["completion", "bash"]) == 0
    assert "complete -F _bqa_complete bqa" in capsys.readouterr().out


def test_bin_wrapper_resolves_global_symlink(tmp_path):
    import os
    import subprocess
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    link = tmp_path / "bqa"
    link.symlink_to(repo_root / "bin" / "bqa")

    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ.get('PATH', '')}"}
    proc = subprocess.run(
        [str(link), "version"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    assert proc.stdout.strip() == "bqa 1.0.0"


def test_usage_error_respects_json_contract(capsys):
    assert main(["--json", "fs"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["ok"] is False
    assert payload["error"]["exit_code"] == 2
    assert "required" in payload["error"]["message"]


def test_cli_install_and_uninstall_scripts(tmp_path):
    import os
    import subprocess
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    target_dir = tmp_path / "bin"
    env = {**os.environ, "BQA_BIN_DIR": str(target_dir)}

    install = subprocess.run(
        [str(repo_root / "scripts" / "install_cli.sh")],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    target = target_dir / "bqa"
    assert target.is_symlink()
    assert target.resolve() == repo_root / "bin" / "bqa"
    assert "Installed bqa" in install.stdout

    version = subprocess.run(
        [str(target), "version"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    assert version.stdout.strip() == "bqa 1.0.0"

    subprocess.run(
        [str(repo_root / "scripts" / "uninstall_cli.sh")],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    assert not target.exists()
    assert not target.is_symlink()


def test_cli_uninstall_refuses_unrelated_target(tmp_path):
    import os
    import subprocess
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    target_dir = tmp_path / "bin"
    target_dir.mkdir()
    unrelated = tmp_path / "unrelated"
    unrelated.write_text("#!/bin/sh\n", encoding="utf-8")
    target = target_dir / "bqa"
    target.symlink_to(unrelated)
    env = {**os.environ, "BQA_BIN_DIR": str(target_dir)}

    proc = subprocess.run(
        [str(repo_root / "scripts" / "uninstall_cli.sh")],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert proc.returncode == 1
    assert target.is_symlink()
    assert "Refusing to remove unrelated executable" in proc.stderr
