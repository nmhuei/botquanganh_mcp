import json
import inspect
import os
from pathlib import Path
import queue
import subprocess
import threading
from types import SimpleNamespace

import pytest

from app.cli.context import CLIContext
from app.cli.desktop_views.i18n import DesktopTranslator
from app.cli.desktop_ui import (
    BQA_UI_DAEMON_ENV,
    DESKTOP_APP_NAME,
    DesktopUIAlreadyRunning,
    _runtime_summary,
    backend_badge,
    completion_fingerprint,
    completion_toast_due,
    desktop_ui_pid_path,
    graphical_session_available,
    launch_desktop_ui_detached,
)
from app.cli.desktop_ui import _DesktopDashboard
from app.cli.main import main


def test_desktop_ui_removes_retired_workflow_stream_contract():
    import app.cli.desktop_ui as desktop_ui

    assert not hasattr(desktop_ui, "StreamRow")
    assert not hasattr(desktop_ui, "make_stream_jobs_reader")
    assert not hasattr(desktop_ui._DesktopDashboard, "_build_runtime_tab")
    assert "stream_reader" not in inspect.signature(desktop_ui.run_desktop_ui).parameters


def test_graphical_session_detection_is_explicit():
    assert graphical_session_available({"DISPLAY": ":0"}) is True
    assert graphical_session_available({"WAYLAND_DISPLAY": "wayland-0"}) is True
    assert graphical_session_available({}) is False


def test_desktop_display_name_is_rebranded_without_changing_the_bqa_command():
    assert DESKTOP_APP_NAME == "UCS-SecretAgent"


def test_desktop_launcher_installs_ucs_name_and_icon(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    fake_bqa = tmp_path / "bqa"
    fake_bqa.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_bqa.chmod(0o755)
    data_home = tmp_path / "data"

    completed = subprocess.run(
        ["bash", "scripts/install_desktop_launcher.sh"],
        cwd=repo_root,
        env={**os.environ, "BQA_BIN": str(fake_bqa), "XDG_DATA_HOME": str(data_home)},
        check=True,
        capture_output=True,
        text=True,
    )

    desktop_entry = (data_home / "applications" / "ucs-secretagent.desktop").read_text()
    assert "Name=UCS-SecretAgent" in desktop_entry
    assert "Icon=ucs-secretagent" in desktop_entry
    assert (data_home / "icons/hicolor/512x512/apps/ucs-secretagent.png").is_file()
    assert completed.returncode == 0


def test_desktop_runtime_summary_covers_ready_degraded_and_stopped():
    assert _runtime_summary({"ok": True})[0] == "Ready"
    assert _runtime_summary({"server": {"running": True}})[0] == "Needs attention"
    assert _runtime_summary({})[0] == "Stopped"


def test_backend_badge_reflects_server_liveness():
    assert backend_badge({"server": {"running": True}}) == (
        "backend: ● alive",
        "#4ade80",
    )
    assert backend_badge({"server": {"running": False}})[0] == "backend: ○ down"
    assert backend_badge({})[0] == "backend: ○ down"


def test_dashboard_refresh_keeps_the_operator_session_and_window_unfocused(tmp_path):
    """A new command elsewhere must not steal the current session or window focus."""
    from app.cli.desktop_views.activity import ActivityView, WorkspaceSession

    class Root:
        def __init__(self):
            self.calls = []

        def deiconify(self):
            self.calls.append("deiconify")

        def lift(self):
            self.calls.append("lift")

        def after(self, _delay, _callback):
            return "refresh-job"

    class Variable:
        def __init__(self, value=""):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    class RuntimeView:
        def render(self, _data):
            return SimpleNamespace(color="#4ade80", summary="Ready")

        def set_message(self, _message):
            pass

    root = Root()
    activity_view = ActivityView(
        root=root,
        tk=type("Tk", (), {"TclError": RuntimeError}),
        ttk=None,
        parent=None,
        workspace_root=lambda: tmp_path,
        on_message=lambda _kind, _message: None,
        on_refresh=lambda: None,
    )
    session_a = WorkspaceSession("chat-a", tmp_path / "chat-a", 1.0)
    session_b = WorkspaceSession("chat-b", tmp_path / "chat-b", 2.0)
    session_a.path.mkdir()
    session_b.path.mkdir()
    activity_view.refresh([session_a, session_b], [])
    assert activity_view.activate_session("chat-a") is True

    dashboard = object.__new__(_DesktopDashboard)
    dashboard.root = root
    dashboard.closed = False
    dashboard.refresh_job = None
    dashboard.status_reader = lambda _repo_root, _values: {"ok": True}
    dashboard.ctx = SimpleNamespace(repo_root=tmp_path, values={"HOST_CHAT_ROOT": str(tmp_path)})
    dashboard.runtime_view = RuntimeView()
    dashboard.status_label = None
    dashboard.backend_label = None
    dashboard.backend_var = Variable()
    dashboard.workspace_var = Variable()
    dashboard.status_var = Variable()
    dashboard.message_var = Variable()
    dashboard.refresh_var = Variable()
    dashboard.busy = False
    dashboard.workspace_selection_dirty = True
    dashboard.activity_view = activity_view
    dashboard.translator = DesktopTranslator("en")
    dashboard.seen_activity_notification_ids = set()
    dashboard.activity_reader = lambda _limit: [
        {"event_id": "event-b", "chat_id": "chat-b", "command": "whoami"}
    ]

    dashboard.refresh()

    assert activity_view.visible_session_ids == {"chat-a", "chat-b"}
    assert activity_view.session_selected_id == "chat-a"
    assert root.calls == []


def test_workspace_log_sse_keeps_the_operator_session_and_window_unfocused(tmp_path):
    """A live SSE event is logged without navigating the desktop UI."""
    from app.cli.desktop_views.activity import ActivityView
    from app.cli.desktop_views.workspace_logs import WorkspaceLogView

    class Root:
        def __init__(self):
            self.calls = []

        def deiconify(self):
            self.calls.append("deiconify")

        def lift(self):
            self.calls.append("lift")

    root = Root()
    activity_view = ActivityView(
        root=root,
        tk=type("Tk", (), {"TclError": RuntimeError}),
        ttk=None,
        parent=None,
        workspace_root=lambda: tmp_path,
        on_message=lambda _kind, _message: None,
        on_refresh=lambda: None,
    )
    assert activity_view.activate_session("chat-a") is True
    dashboard = object.__new__(_DesktopDashboard)
    dashboard.activity_view = activity_view
    dashboard.translator = DesktopTranslator("en")
    dashboard.seen_activity_notification_ids = set()
    dashboard._set_message = lambda _kind, _message: None
    workspace_logs = WorkspaceLogView(on_new_activity=dashboard._on_workspace_activity)

    workspace_logs.accept_event(
        {
            "id": "event-b",
            "event": "workspace_log",
            "data": {
                "chat_id": "chat-b",
                "interaction_id": "operation-b",
                "event_action": "host_run_command",
            },
        }
    )

    assert [row.chat_id for row in workspace_logs.rows] == ["chat-b"]
    assert activity_view.visible_session_ids == {"chat-a", "chat-b"}
    assert activity_view.session_selected_id == "chat-a"
    assert root.calls == []


def test_dashboard_language_change_persists_then_relabels_every_live_view(monkeypatch, tmp_path):
    class Variable:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    class Bindings:
        def __init__(self):
            self.translators = []

        def set_translator(self, translator):
            self.translators.append(translator)

    class Notebook:
        def __init__(self):
            self.calls = []

        def tab(self, tab, **values):
            self.calls.append((tab, values))

    class View:
        def __init__(self):
            self.translators = []

        def set_translator(self, translator):
            self.translators.append(translator)

    dashboard = object.__new__(_DesktopDashboard)
    dashboard.ctx = type("Context", (), {"repo_root": tmp_path, "values": {}})()
    dashboard.translator = DesktopTranslator("en")
    dashboard.header_bindings = Bindings()
    dashboard.language_display_var = Variable("Tiếng Việt")
    dashboard.language_combo = None
    dashboard.language_choices = {"English": "en", "Tiếng Việt": "vi"}
    dashboard.notebook = Notebook()
    dashboard.notebook_tabs = {
        "runtime": "runtime-tab",
        "workspace_logs": "logs-tab",
        "gpt_activity": "activity-tab",
    }
    dashboard.runtime_view = View()
    dashboard.activity_view = View()
    dashboard.workspace_log_view = View()
    messages = []
    dashboard._set_message = lambda kind, message: messages.append((kind, message))
    persisted = []
    monkeypatch.setattr(
        "app.cli.desktop_ui.set_desktop_ui_language",
        lambda root, language: persisted.append((root, language)) or {"BQA_UI_LANGUAGE": language},
    )

    dashboard.change_language()

    assert persisted == [(tmp_path, "vi")]
    assert dashboard.ctx.values["BQA_UI_LANGUAGE"] == "vi"
    assert dashboard.notebook.calls == [
        ("runtime-tab", {"text": "Runtime"}),
        ("logs-tab", {"text": "Nhật ký Workspace"}),
        ("activity-tab", {"text": "Hoạt động GPT"}),
    ]
    assert all(view.translators[-1].language == "vi" for view in (
        dashboard.runtime_view,
        dashboard.activity_view,
        dashboard.workspace_log_view,
    ))
    assert messages == [("success", "Đã đổi ngôn ngữ sang Tiếng Việt.")]


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


def test_lifecycle_worker_delivers_result_through_main_thread_queue():
    main_thread = threading.get_ident()
    completed = threading.Event()

    class Root:
        def __init__(self):
            self.after_threads = []
            self.callbacks = []

        def after(self, _delay, callback):
            self.after_threads.append(threading.get_ident())
            self.callbacks.append(callback)
            return len(self.callbacks)

        def after_cancel(self, _job):
            pass

        def run_next(self):
            self.callbacks.pop(0)()

    class RuntimeView:
        def set_message(self, _message):
            pass

        def set_busy(self, _busy):
            pass

    dashboard = object.__new__(_DesktopDashboard)
    dashboard.root = Root()
    dashboard.closed = False
    dashboard.busy = False
    dashboard.action_queue = queue.Queue()
    dashboard.action_drain_job = None
    dashboard.action_started_at = None
    dashboard.action_start_fingerprint = None
    dashboard.latest_status_data = {}
    dashboard.runtime_view = RuntimeView()
    dashboard.translator = DesktopTranslator()
    dashboard._finish_action = lambda kind, text, elapsed_seconds: completed.set()

    dashboard._run_action("start", lambda: completed.clear() or {"ok": True})
    assert completed.wait(timeout=1) is False
    assert dashboard.action_queue.qsize() == 1
    assert dashboard.root.after_threads == [main_thread]

    dashboard.root.run_next()

    assert completed.is_set()
    assert all(thread_id == main_thread for thread_id in dashboard.root.after_threads)


def test_ui_command_uses_desktop_window(monkeypatch):
    called = []
    monkeypatch.delenv(BQA_UI_DAEMON_ENV, raising=False)
    monkeypatch.setattr("app.cli.desktop_ui.run_desktop_ui", lambda ctx: called.append(ctx) or 0)

    assert main(["ui", "--inline"]) == 0
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


def test_foreground_ui_is_a_detached_compatibility_alias(monkeypatch, capsys):
    started = []
    monkeypatch.setattr("app.cli.desktop_ui.graphical_session_available", lambda: True)
    monkeypatch.setattr(
        "app.cli.desktop_ui.launch_desktop_ui_detached",
        lambda _ctx: started.append(True) or 1357,
    )

    assert main(["ui", "--foreground", "--quiet"]) == 0
    assert capsys.readouterr().out.strip() == "1357"
    assert started == [True]


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

    assert main(["ui"]) == 0
    assert observed["content"] == str(real_pid)
    assert not desktop_ui_pid_path(tmp_path).exists()


def test_inline_ui_without_env_marker_never_touches_the_pid_file(monkeypatch, tmp_path):
    monkeypatch.setattr("app.cli.context.repo_root", lambda: tmp_path)
    monkeypatch.delenv(BQA_UI_DAEMON_ENV, raising=False)
    monkeypatch.setattr("app.cli.desktop_ui.run_desktop_ui", lambda _ctx: 0)

    assert main(["ui", "--inline"]) == 0
    assert not desktop_ui_pid_path(tmp_path).exists()


def test_desktop_activity_root_uses_host_chat_root(tmp_path):
    configured = tmp_path / "real-chat-workspaces"
    dashboard = object.__new__(_DesktopDashboard)
    dashboard.ctx = type(
        "Context",
        (),
        {
            "repo_root": tmp_path / "repo",
            "values": {
                "HOST_CHAT_ROOT": str(configured),
                "BQA_CHAT_WORKSPACES_DIR": str(tmp_path / "wrong-root"),
            },
        },
    )()

    assert dashboard.chat_workspaces_root() == configured
