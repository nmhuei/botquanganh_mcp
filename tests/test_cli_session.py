"""CLI tests for 'bqa session' subcommands."""

import json
from pathlib import Path

import app.config
from app.cli.main import main


def test_cli_session_list_and_bind(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(app.config, "HOST_CHAT_ROOT", tmp_path)
    monkeypatch.setattr("app.cli.chats_view._workspaces_root", lambda: tmp_path)
    monkeypatch.setattr("app.cli.commands.session._workspaces_root", lambda: tmp_path)

    # 1. Create a dummy session folder
    sess_dir = tmp_path / "cw-20260916-test-cli-12345678"
    sess_dir.mkdir(parents=True)
    (sess_dir / "meta.json").write_text(
        json.dumps({"created_at": "2026-09-16T12:00:00Z", "label": "test-cli"}),
        encoding="utf-8",
    )
    (sess_dir / "journal.jsonl").write_text(
        json.dumps({"type": "op_result", "ok": True, "details": {"command": "pytest"}}) + "\n",
        encoding="utf-8",
    )

    # Test bqa session list --json
    rc = main(["session", "list", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["ok"] is True
    assert data["total"] == 1
    assert data["sessions"][0]["session_id"] == "cw-20260916-test-cli-12345678"

    # Test bqa session bind
    rc_bind = main(["session", "bind", "cw-20260916-test-cli-12345678", "--json"])
    assert rc_bind == 0
    out_bind = capsys.readouterr().out
    bind_data = json.loads(out_bind)
    assert bind_data["ok"] is True
    assert bind_data["status"] == "active"
    assert bind_data["session_id"] == "cw-20260916-test-cli-12345678"

    # Test bqa session current --json
    rc_curr = main(["session", "current", "--json"])
    assert rc_curr == 0
    curr_data = json.loads(capsys.readouterr().out)
    assert curr_data["ok"] is True
    assert curr_data["session_id"] == "cw-20260916-test-cli-12345678"


def test_cli_session_quiet_mode(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(app.config, "HOST_CHAT_ROOT", tmp_path)
    monkeypatch.setattr("app.cli.commands.session._workspaces_root", lambda: tmp_path)

    sess_dir = tmp_path / "cw-20260916-quiet-abcdef12"
    sess_dir.mkdir(parents=True)
    (sess_dir / "meta.json").write_text("{}", encoding="utf-8")

    rc = main(["session", "list", "--quiet"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert "cw-20260916-quiet-abcdef12" in out
