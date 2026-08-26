from io import StringIO

from app.cli.context import CLIContext
from app.cli.desktop_ui import _runtime_summary, graphical_session_available, launch_desktop_ui_detached
from app.cli.main import main


def test_graphical_session_detection_is_explicit():
    assert graphical_session_available({"DISPLAY": ":0"}) is True
    assert graphical_session_available({"WAYLAND_DISPLAY": "wayland-0"}) is True
    assert graphical_session_available({}) is False


def test_desktop_runtime_summary_covers_ready_degraded_and_stopped():
    assert _runtime_summary({"ok": True})[0] == "Sẵn sàng"
    assert _runtime_summary({"server": {"running": True}})[0] == "Cần kiểm tra"
    assert _runtime_summary({})[0] == "Đã dừng"


def test_ui_command_uses_desktop_window(monkeypatch):
    called = []
    monkeypatch.setattr("app.cli.desktop_ui.run_desktop_ui", lambda ctx: called.append(ctx) or 0)

    assert main(["ui"]) == 0
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
