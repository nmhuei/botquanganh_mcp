
import app.cli.lifecycle as lifecycle


def test_connector_url_uses_only_canonical_file(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "cloudflared.log").write_text("https://old.trycloudflare.com\n")
    assert lifecycle.connector_url(tmp_path, {"MCP_PATH": "/mcp"}) is None
    (logs / "tunnel_url.txt").write_text("https://fresh.trycloudflare.com\n")
    assert lifecycle.connector_url(tmp_path, {"MCP_PATH": "/mcp"}) == "https://fresh.trycloudflare.com/mcp"


def test_status_data_reads_pid_files(monkeypatch, tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    for name, pid in {"watchdog": 10, "server": 20, "tunnel": 30}.items():
        (logs / f"{name}.pid").write_text(str(pid))
    (logs / "tunnel_url.txt").write_text("https://fresh.trycloudflare.com\n")
    monkeypatch.setattr(
        lifecycle,
        "process_matches",
        lambda pid, kind: (pid, kind) in {(10, "supervisor"), (20, "server"), (30, "tunnel")},
    )
    monkeypatch.setattr(lifecycle, "bridge_ready", lambda values: True)
    result = lifecycle.status_data(
        tmp_path,
        {
            "MCP_PATH": "/mcp",
            "REQUIRE_AUTH": "false",
            "HOST_WORKSPACE_DIR": str(tmp_path),
        },
    )
    assert result["ok"] is True
    assert result["supervisor"]["pid"] == 10
    assert result["url"] == "https://fresh.trycloudflare.com/mcp"
    assert result["auth_required"] is False


def test_server_restart_requires_tunnel_to_be_preserved(monkeypatch, tmp_path):
    before = {
        "server": {"running": True, "pid": 1},
        "tunnel": {"running": True, "pid": 2},
        "bridge": "ready",
        "url": "https://same.trycloudflare.com/mcp",
    }
    after = {
        "server": {"running": True, "pid": 3},
        "tunnel": {"running": True, "pid": 2},
        "bridge": "ready",
        "url": "https://same.trycloudflare.com/mcp",
    }
    states = iter([before, after])
    monkeypatch.setattr(lifecycle, "status_data", lambda *_args: next(states))
    monkeypatch.setattr(
        lifecycle,
        "run_script",
        lambda *_args, **_kwargs: {"ok": True, "stdout": "restarted\n", "stderr": ""},
    )
    result = lifecycle.server_restart(tmp_path, {})
    assert result["ok"] is True
    assert result["tunnel_preserved"] is True


def test_run_script_maps_arguments(tmp_path):
    script = tmp_path / "run.sh"
    script.write_text("#!/usr/bin/env bash\nprintf '%s' \"$1\"\n")
    script.chmod(0o755)
    result = lifecycle.run_script(tmp_path, "run.sh", ["status"])
    assert result["ok"] is True
    assert result["stdout"] == "status"
