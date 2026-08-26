import json
import os

import pytest

from app.cli.context import CLIContext
from app.cli.desktop_ui import (
    BQA_UI_DAEMON_ENV,
    DesktopUIAlreadyRunning,
    _runtime_summary,
    backend_badge,
    completion_fingerprint,
    completion_toast_due,
    desktop_ui_pid_path,
    graphical_session_available,
    launch_desktop_ui_detached,
)
from app.cli.main import main


def test_graphical_session_detection_is_explicit():
    assert graphical_session_available({"DISPLAY": ":0"}) is True
    assert graphical_session_available({"WAYLAND_DISPLAY": "wayland-0"}) is True
    assert graphical_session_available({}) is False


def test_desktop_runtime_summary_covers_ready_degraded_and_stopped():
    assert _runtime_summary({"ok": True})[0] == "Sẵn sàng"
    assert _runtime_summary({"server": {"running": True}})[0] == "Cần kiểm tra"
    assert _runtime_summary({})[0] == "Đã dừng"


def test_backend_badge_reflects_server_liveness():
    assert backend_badge({"server": {"running": True}}) == (
        "backend: ● alive",
        "#147a45",
    )
    assert backend_badge({"server": {"running": False}})[0] == "backend: ○ down"
    assert backend_badge({})[0] == "backend: ○ down"


def test_completion_fingerprint_tracks_runtime_fields_only():
    base = {
        "ok": True,
        "bridge": "ready",
        "url_state": "active",
        "server": {"running": True, "pid": 10},
        "tunnel": {"running": True, "pid": 11},
        "workspace": "/tmp/ignored",
    }
    same_runtime = {**base, "workspace": "/somewhere/else"}
    changed_runtime = {**base, "server": {"running": False, "pid": None}}

    assert completion_fingerprint(base) == completion_fingerprint(same_runtime)
    assert completion_fingerprint(base) != completion_fingerprint(changed_runtime)


def test_completion_toast_gate_is_one_shot_and_transition_only():
    # Too fresh: operation finished under the 10s threshold.
    assert completion_toast_due(9.9, "aaa", "bbb", None) is False
    # First eligible completion fires.
    assert completion_toast_due(12.0, "aaa", "bbb", None) is True
    # The same completion never fires twice.
    assert completion_toast_due(20.0, "aaa", "bbb", "bbb") is False
    # Status never flipped away from the start snapshot: no done transition.
    assert completion_toast_due(20.0, "aaa", "aaa", None) is False
    # Missing start snapshot still allows a single fire.
    assert completion_toast_due(12.0, None, "bbb", None) is True


def test_ui_command_uses_desktop_window(monkeypatch):
    called = []
    monkeypatch.delenv(BQA_UI_DAEMON_ENV, raising=False)
    monkeypatch.setattr("app.cli.desktop_ui.run_desktop_ui", lambda ctx: called.append(ctx) or 0)

    assert main(["ui", "--foreground"]) == 0
    assert len(called) == 1
    assert isinstance(called[0], CLIContext)


def test_ui_detach_starts_independent_process(monkeypatch, tmp_path):
    started = {}

    class Process:
        pid = 4567

    def fake_popen(command, **kwargs):
        started["command"] = command
        started["kwargs"] = kwargs
        return Process()

    monkeypatch.setattr("app.cli.desktop_ui.subprocess.Popen", fake_popen)
    ctx = type("Context", (), {"repo_root": tmp_path})()

    assert launch_desktop_ui_detached(ctx) == 4567
    assert started["command"][-2:] == ["app.cli.main", "ui"]
    assert started["kwargs"]["cwd"] == tmp_path
    assert started["kwargs"]["start_new_session"] is True


def test_ui_detach_dispatches_to_background_launcher(monkeypatch, capsys):
    started = []
    monkeypatch.setattr("app.cli.desktop_ui.graphical_session_available", lambda: True)
    monkeypatch.setattr(
        "app.cli.desktop_ui.launch_desktop_ui_detached",
        lambda _ctx: started.append(True) or 8765,
    )

    assert main(["ui", "--detach", "--quiet"]) == 0
    assert capsys.readouterr().out.strip() == "8765"
    assert started == [True]


def test_default_ui_detaches_instead_of_opening_inline(monkeypatch, capsys):
    opened_inline = []
    monkeypatch.setattr("app.cli.desktop_ui.graphical_session_available", lambda: True)
    monkeypatch.setattr(
        "app.cli.desktop_ui.run_desktop_ui",
        lambda _ctx: opened_inline.append(True) or 0,
    )
    monkeypatch.setattr(
        "app.cli.desktop_ui.launch_desktop_ui_detached",
        lambda _ctx: 2468,
    )

    assert main(["ui", "--quiet"]) == 0
    assert capsys.readouterr().out.strip() == "2468"
    assert opened_inline == []


def test_launch_writes_pid_file_and_env_marker(monkeypatch, tmp_path):
    captured = {}

    class Process:
        pid = 4567

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Process()

    monkeypatch.setenv("BQA_UI_DAEMON_ENV_SENTINEL", "keep-me")
    monkeypatch.setattr("app.cli.desktop_ui.subprocess.Popen", fake_popen)
    ctx = type("Context", (), {"repo_root": tmp_path})()

    assert launch_desktop_ui_detached(ctx) == 4567
    assert captured["kwargs"]["env"][BQA_UI_DAEMON_ENV] == "1"
    assert captured["kwargs"]["env"]["BQA_UI_DAEMON_ENV_SENTINEL"] == "keep-me"
    assert desktop_ui_pid_path(tmp_path).read_text(encoding="utf-8") == "4567\n"


def test_launch_refuses_duplicate_while_detached_instance_is_live(monkeypatch, tmp_path):
    pid_path = desktop_ui_pid_path(tmp_path)
    pid_path.parent.mkdir(parents=True)
    pid_path.write_text("1234\n", encoding="utf-8")
    monkeypatch.setattr(
        "app.cli.desktop_ui.process_command_line",
        lambda pid: f"/usr/bin/python3 -m app.cli.main ui --foreground pid={pid}",
    )
    ctx = type("Context", (), {"repo_root": tmp_path})()

    with pytest.raises(DesktopUIAlreadyRunning) as excinfo:
        launch_desktop_ui_detached(ctx)
    assert excinfo.value.pid == 1234


def test_launch_ignores_stale_pid_file_and_reclaims_it(monkeypatch, tmp_path):
    pid_path = desktop_ui_pid_path(tmp_path)
    pid_path.parent.mkdir(parents=True)
    pid_path.write_text("99999\n", encoding="utf-8")
    monkeypatch.setattr("app.cli.desktop_ui.process_command_line", lambda pid: "")

    class Process:
        pid = 5555

    monkeypatch.setattr("app.cli.desktop_ui.subprocess.Popen", lambda command, **kwargs: Process())
    ctx = type("Context", (), {"repo_root": tmp_path})()

    assert launch_desktop_ui_detached(ctx) == 5555
    assert pid_path.read_text(encoding="utf-8") == "5555\n"


def test_main_reports_already_running_without_spawning(monkeypatch, capsys):
    monkeypatch.setattr("app.cli.desktop_ui.graphical_session_available", lambda: True)

    def raise_already_running(_ctx):
        raise DesktopUIAlreadyRunning(4321)

    monkeypatch.setattr(
        "app.cli.desktop_ui.launch_desktop_ui_detached", raise_already_running
    )

    assert main(["ui", "--quiet"]) == 0
    assert capsys.readouterr().out.strip() == "4321"

    assert main(["ui", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "already_running"
    assert payload["pid"] == 4321


def test_daemon_child_registers_and_releases_the_pid_file(monkeypatch, tmp_path):
    observed = {}
    real_pid = os.getpid()

    def fake_run_desktop_ui(ctx):
        path = desktop_ui_pid_path(ctx.repo_root)
        observed["content"] = path.read_text(encoding="utf-8").strip()
        return 0

    monkeypatch.setattr("app.cli.context.repo_root", lambda: tmp_path)
    monkeypatch.setenv(BQA_UI_DAEMON_ENV, "1")
    monkeypatch.setattr("app.cli.desktop_ui.run_desktop_ui", fake_run_desktop_ui)

    assert main(["ui", "--foreground"]) == 0
    assert observed["content"] == str(real_pid)
    assert not desktop_ui_pid_path(tmp_path).exists()


def test_foreground_without_env_marker_never_touches_the_pid_file(monkeypatch, tmp_path):
    monkeypatch.setattr("app.cli.context.repo_root", lambda: tmp_path)
    monkeypatch.delenv(BQA_UI_DAEMON_ENV, raising=False)
    monkeypatch.setattr("app.cli.desktop_ui.run_desktop_ui", lambda _ctx: 0)

    assert main(["ui", "--foreground"]) == 0
    assert not desktop_ui_pid_path(tmp_path).exists()
