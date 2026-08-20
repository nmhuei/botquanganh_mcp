
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
    assert result["url_state"] == "active"
    assert result["connector_ready"] is True
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


def test_dead_tunnel_preserves_last_known_url_as_stale(monkeypatch, tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "server.pid").write_text("20")
    (logs / "tunnel.pid").write_text("30")
    (logs / "tunnel_url.txt").write_text("https://stale.trycloudflare.com\n")
    monkeypatch.setattr(
        lifecycle, "process_matches", lambda pid, kind: (pid, kind) == (20, "server")
    )
    monkeypatch.setattr(lifecycle, "bridge_ready", lambda values: True)
    result = lifecycle.status_data(
        tmp_path, {"MCP_PATH": "/mcp", "HOST_WORKSPACE_DIR": str(tmp_path)}
    )
    assert result["ok"] is False
    assert result["connector_ready"] is False
    assert result["url"] is None
    assert result["url_state"] == "stale"
    assert result["last_known_url"] == "https://stale.trycloudflare.com/mcp"


def test_restart_delegates_to_canonical_server_restart(monkeypatch, tmp_path):
    expected = {"ok": True, "operation": "server_restart"}
    monkeypatch.setattr(lifecycle, "server_restart", lambda root, values: expected)
    assert lifecycle.restart(tmp_path, {"MCP_PORT": "9000"}) is expected


def test_cli_start_uses_run_mcp_compatibility_backend(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        lifecycle,
        "run_script",
        lambda root, path, arguments=(), **kwargs: calls.append(
            (root, path, list(arguments), kwargs)
        )
        or {"ok": True},
    )
    assert lifecycle.start(tmp_path) == {"ok": True}
    assert calls == [(tmp_path, "run_mcp_tunnel.sh", ["start"], {})]


def test_run_script_maps_arguments(tmp_path):
    script = tmp_path / "run.sh"
    script.write_text("#!/usr/bin/env bash\nprintf '%s' \"$1\"\n")
    script.chmod(0o755)
    result = lifecycle.run_script(tmp_path, "run.sh", ["status"])
    assert result["ok"] is True
    assert result["stdout"] == "status"
