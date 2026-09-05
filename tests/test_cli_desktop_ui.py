import json
import inspect
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import types
from types import SimpleNamespace

import pytest

from app.cli.context import CLIContext
from app.cli.desktop_views.i18n import DesktopTranslator, TranslationBindings
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
from app.cli.desktop_views.theme import PALETTE


class ShellVariable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class ShellWidget:
    def __init__(self, parent=None, **values):
        self.parent = parent
        self.configured = dict(values)
        self.grid_calls = []
        self.pack_calls = []
        self.bind_calls = []

    def configure(self, **values):
        self.configured.update(values)

    def grid(self, **values):
        self.grid_calls.append(values)

    def pack(self, **values):
        self.pack_calls.append(values)

    def bind(self, event, callback):
        self.bind_calls.append((event, callback))

    def columnconfigure(self, *_args, **_values):
        pass

    def rowconfigure(self, *_args, **_values):
        pass


class ShellButton(ShellWidget):
    def invoke(self):
        return self.configured["command"]()


class ShellNotebook(ShellWidget):
    def __init__(self, parent=None, **values):
        super().__init__(parent, **values)
        self.tabs = []
        self.selected = ""
        self.select_calls = []
        self.tab_calls = []

    def add(self, tab):
        self.tabs.append(tab)
        if not self.selected:
            self.selected = tab

    def select(self, tab=None):
        if tab is not None:
            self.select_calls.append(tab)
            self.selected = tab
        return self.selected

    def tab(self, tab, **values):
        self.tab_calls.append((tab, values))


class ShellTtk:
    def __init__(self):
        self.frames = []
        self.labels = []
        self.buttons = []
        self.comboboxes = []
        self.notebooks = []

    def Style(self, root):
        return ShellWidget(root)

    def Frame(self, parent=None, **values):
        widget = ShellWidget(parent, **values)
        self.frames.append(widget)
        return widget

    def Label(self, parent=None, **values):
        widget = ShellWidget(parent, **values)
        self.labels.append(widget)
        return widget

    def Button(self, parent=None, **values):
        widget = ShellButton(parent, **values)
        self.buttons.append(widget)
        return widget

    def Combobox(self, parent=None, **values):
        widget = ShellWidget(parent, **values)
        self.comboboxes.append(widget)
        return widget

    def Notebook(self, parent=None, **values):
        widget = ShellNotebook(parent, **values)
        self.notebooks.append(widget)
        return widget


class ShellRoot(ShellWidget):
    def title(self, value):
        self.title_value = value

    def geometry(self, value):
        self.geometry_value = value

    def minsize(self, width, height):
        self.minimum_size = (width, height)


class RecordingBindings(TranslationBindings):
    def __init__(self, translator):
        super().__init__(translator)
        self.records = []

    def bind(self, widget, key, **values):
        self.records.append((widget, key))
        super().bind(widget, key, **values)


class ShellRuntimeView:
    def __init__(self):
        self.build_values = {}
        self.translators = []
        self.messages = []

    def build(self, **values):
        self.build_values = values

    def set_translator(self, translator):
        self.translators.append(translator)

    def set_message(self, message):
        self.messages.append(message)


class ShellActivityView:
    def __init__(self, **values):
        self.build_values = values
        self.translators = []

    def set_activity_tab(self, notebook, tab):
        self.activity_tab = (notebook, tab)

    def set_translator(self, translator):
        self.translators.append(translator)


class ShellWorkspaceLogView:
    def __init__(self, **values):
        self.build_values = values
        self.translators = []

    def set_translator(self, translator):
        self.translators.append(translator)


def build_dashboard_shell(monkeypatch, tmp_path):
    ttk = ShellTtk()
    dashboard = object.__new__(_DesktopDashboard)
    dashboard.root = ShellRoot()
    dashboard.tk = type("Tk", (), {"TclError": Exception})()
    dashboard.ttk = ttk
    dashboard.ctx = type(
        "Context",
        (),
        {"repo_root": tmp_path, "values": {"BQA_UI_LANGUAGE": "en"}},
    )()
    dashboard.translator = DesktopTranslator("en")
    dashboard.header_bindings = TranslationBindings(dashboard.translator)
    dashboard.navigation_bindings = RecordingBindings(dashboard.translator)
    dashboard.language_choices = {}
    dashboard.language_display_var = ShellVariable()
    dashboard.language_combo = None
    dashboard.notebook = None
    dashboard.notebook_tabs = {}
    dashboard.navigation_buttons = {}
    dashboard.footer_bindings = {}
    dashboard.runtime_view = ShellRuntimeView()
    dashboard.status_var = ShellVariable("Loading")
    dashboard.backend_var = ShellVariable("backend")
    dashboard.message_var = ShellVariable()
    dashboard.workspace_var = ShellVariable("/workspace")
    dashboard.refresh_var = ShellVariable("refresh: —")
    dashboard.sse_var = ShellVariable("SSE: CONNECTING")
    dashboard.status_label = None
    dashboard.backend_label = None
    dashboard.activity_view = None
    dashboard.workspace_log_view = None

    monkeypatch.setattr("app.cli.desktop_ui.load_desktop_icon", lambda _root, _tk: None)
    monkeypatch.setattr("app.cli.desktop_ui.apply_desktop_theme", lambda _style, _root: None)
    monkeypatch.setattr("app.cli.desktop_ui.ActivityView", ShellActivityView)
    monkeypatch.setattr("app.cli.desktop_ui.WorkspaceLogView", ShellWorkspaceLogView)

    dashboard._build(None, object())
    return dashboard, ttk


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
        PALETTE["success"],
    )
    assert backend_badge({"server": {"running": False}})[0] == "backend: ○ down"
    assert backend_badge({})[0] == "backend: ○ down"


def test_dashboard_build_creates_one_notebook_three_tabs_and_passive_header(
    monkeypatch, tmp_path
):
    dashboard, ttk = build_dashboard_shell(monkeypatch, tmp_path)

    assert len(ttk.notebooks) == 1
    notebook = ttk.notebooks[0]
    assert tuple(notebook.tabs) == tuple(dashboard.notebook_tabs.values())
    assert tuple(dashboard.notebook_tabs) == (
        "runtime",
        "workspace_logs",
        "gpt_activity",
    )
    assert notebook.bind_calls == [
        ("<<NotebookTabChanged>>", dashboard._sync_navigation)
    ]

    rail_buttons = [
        button
        for button in ttk.buttons
        if button.parent.configured.get("style") == "Rail.TFrame"
    ]
    header_buttons = [button for button in ttk.buttons if button not in rail_buttons]
    assert len(rail_buttons) == 3
    assert len(header_buttons) == 1
    assert header_buttons[0].configured["command"] == dashboard.close
    assert all(
        header_buttons[0].configured["command"] != action
        for action in (
            dashboard.start_service,
            dashboard.restart_bridge,
            dashboard.refresh,
        )
    )
    assert len(ttk.comboboxes) == 1
    assert ttk.comboboxes[0].parent is header_buttons[0].parent


def test_dashboard_build_wires_translated_rail_to_existing_notebook_without_recursion(
    monkeypatch, tmp_path
):
    dashboard, ttk = build_dashboard_shell(monkeypatch, tmp_path)
    notebook = ttk.notebooks[0]
    expected_keys = (
        "nav.runtime",
        "nav.workspace_logs",
        "nav.gpt_activity",
    )
    assert tuple(key for _button, key in dashboard.navigation_bindings.records) == (
        expected_keys
    )

    buttons_by_key = {
        key.removeprefix("nav."): button
        for button, key in dashboard.navigation_bindings.records
    }
    assert buttons_by_key == dashboard.navigation_buttons
    for key, tab in dashboard.notebook_tabs.items():
        notebook.selected = object()
        notebook.select_calls.clear()
        buttons_by_key[key].invoke()
        assert notebook.selected is tab
        assert notebook.select_calls == [tab]
        assert buttons_by_key[key].configured["style"] == "RailActive.TButton"

    notebook.selected = dashboard.notebook_tabs["workspace_logs"]
    notebook.select_calls.clear()
    dashboard._sync_navigation()
    assert notebook.select_calls == []
    assert dashboard.navigation_buttons["workspace_logs"].configured["style"] == (
        "RailActive.TButton"
    )
    assert dashboard.navigation_buttons["runtime"].configured["style"] == (
        "Rail.TButton"
    )

    monkeypatch.setattr(
        "app.cli.desktop_ui.set_desktop_ui_language",
        lambda _root, language: {"BQA_UI_LANGUAGE": language},
    )
    dashboard.language_display_var.set("Tiếng Việt")
    dashboard.change_language()
    assert tuple(
        dashboard.navigation_buttons[key].configured["text"]
        for key in dashboard.notebook_tabs
    ) == ("Runtime", "Nhật ký Workspace", "Hoạt động GPT")


def test_dashboard_navigation_selects_named_notebook_tab_and_marks_only_it_active():
    class Notebook:
        def __init__(self):
            self.selected = "runtime-tab"

        def select(self, tab=None):
            if tab is not None:
                self.selected = tab
            return self.selected

        def tab(self, _tab, **_values):
            pass

        def bind(self, _event, _callback):
            pass

    class Button:
        def __init__(self):
            self.configured = {}

        def configure(self, **values):
            self.configured.update(values)

    dashboard = object.__new__(_DesktopDashboard)
    dashboard.notebook = Notebook()
    dashboard.notebook_tabs = {
        "runtime": "runtime-tab",
        "workspace_logs": "workspace-tab",
        "gpt_activity": "activity-tab",
    }
    dashboard.navigation_buttons = {
        "runtime": Button(),
        "workspace_logs": Button(),
        "gpt_activity": Button(),
    }

    dashboard._select_view("workspace_logs")

    assert dashboard.notebook.selected == "workspace-tab"
    assert dashboard.navigation_buttons["workspace_logs"].configured["style"] == (
        "RailActive.TButton"
    )
    assert dashboard.navigation_buttons["runtime"].configured["style"] == (
        "Rail.TButton"
    )
    assert dashboard.navigation_buttons["gpt_activity"].configured["style"] == (
        "Rail.TButton"
    )


def test_dashboard_navigation_syncs_rail_when_notebook_selection_changes_elsewhere():
    class Notebook:
        def select(self):
            return "activity-tab"

    class Button:
        def __init__(self):
            self.configured = {}

        def configure(self, **values):
            self.configured.update(values)

    dashboard = object.__new__(_DesktopDashboard)
    dashboard.notebook = Notebook()
    dashboard.notebook_tabs = {
        "runtime": "runtime-tab",
        "workspace_logs": "workspace-tab",
        "gpt_activity": "activity-tab",
    }
    dashboard.navigation_buttons = {
        key: Button() for key in dashboard.notebook_tabs
    }

    dashboard._sync_navigation()

    assert dashboard.navigation_buttons["gpt_activity"].configured["style"] == (
        "RailActive.TButton"
    )
    assert dashboard.navigation_buttons["runtime"].configured["style"] == (
        "Rail.TButton"
    )


def test_dashboard_footer_labels_stay_bound_to_existing_status_variables():
    class Widget:
        def __init__(self, parent=None, **values):
            self.parent = parent
            self.configured = dict(values)

        def grid(self, **_values):
            pass

        def columnconfigure(self, *_args, **_values):
            pass

    class Ttk:
        Frame = Widget
        Label = Widget

    dashboard = object.__new__(_DesktopDashboard)
    dashboard.ttk = Ttk()
    dashboard.backend_var = object()
    dashboard.workspace_var = object()
    dashboard.refresh_var = object()
    dashboard.sse_var = object()
    dashboard.message_var = object()
    dashboard.footer_bindings = {}

    dashboard._build_footer(Widget())

    assert set(dashboard.footer_bindings) == {
        "backend",
        "workspace",
        "refresh",
        "sse",
        "message",
    }
    assert dashboard.footer_bindings["backend"].configured["textvariable"] is (
        dashboard.backend_var
    )
    assert dashboard.footer_bindings["workspace"].configured["textvariable"] is (
        dashboard.workspace_var
    )
    assert dashboard.footer_bindings["refresh"].configured["textvariable"] is (
        dashboard.refresh_var
    )
    assert dashboard.footer_bindings["sse"].configured["textvariable"] is (
        dashboard.sse_var
    )
    assert dashboard.footer_bindings["message"].configured["textvariable"] is (
        dashboard.message_var
    )
    assert all(
        label.configured["style"] == "Footer.TLabel"
        for label in dashboard.footer_bindings.values()
    )


def test_dashboard_navigation_shell_wires_existing_safe_runtime_actions_once():
    class RuntimeView:
        def build(self, **values):
            self.build_values = values

    dashboard = object.__new__(_DesktopDashboard)
    dashboard.ttk = object()
    dashboard.runtime_view = RuntimeView()
    dashboard.workspace_var = object()
    dashboard.copy_endpoint = lambda: None
    dashboard.choose_workspace = lambda: None
    dashboard.apply_workspace = lambda: None
    calls = []
    dashboard.start_service = lambda: calls.append("start")
    dashboard.stop_service = lambda: calls.append("stop")
    dashboard.restart_bridge = lambda: calls.append("restart")
    dashboard.refresh = lambda: calls.append("refresh")

    dashboard._build_runtime_view("runtime-tab")

    callbacks = dashboard.runtime_view.build_values
    assert callbacks["on_start"] is dashboard.start_service
    assert callbacks["on_stop"] is dashboard.stop_service
    assert callbacks["on_restart"] is dashboard.restart_bridge
    assert callbacks["on_refresh"] is dashboard.refresh
    callbacks["on_start"]()
    callbacks["on_stop"]()
    callbacks["on_restart"]()
    callbacks["on_refresh"]()
    assert calls == ["start", "stop", "restart", "refresh"]


def test_stop_cancellation_launches_no_lifecycle_action(tmp_path):
    dashboard = object.__new__(_DesktopDashboard)
    dashboard.root = object()
    dashboard.ctx = type("Context", (), {"repo_root": tmp_path})()
    dashboard.translator = DesktopTranslator()
    dashboard.stop_confirmation = lambda _root, _translator: False
    lifecycle_calls = []
    dashboard.stop_action = lambda repo_root: lifecycle_calls.append(repo_root)
    queued_actions = []
    dashboard._run_action = lambda label, action: queued_actions.append((label, action))

    dashboard.stop_service()

    assert queued_actions == []
    assert lifecycle_calls == []


def test_confirmed_stop_uses_existing_lifecycle_worker_path(tmp_path):
    dashboard = object.__new__(_DesktopDashboard)
    dashboard.root = object()
    dashboard.ctx = type("Context", (), {"repo_root": tmp_path})()
    dashboard.translator = DesktopTranslator()
    dashboard.stop_confirmation = lambda _root, _translator: True
    lifecycle_calls = []
    dashboard.stop_action = (
        lambda repo_root: lifecycle_calls.append(repo_root) or {"ok": True}
    )
    queued_actions = []
    dashboard._run_action = lambda label, action: queued_actions.append((label, action))

    dashboard.stop_service()

    assert len(queued_actions) == 1
    assert queued_actions[0][0] == DesktopTranslator().text("action.stop")
    assert lifecycle_calls == []
    assert queued_actions[0][1]() == {"ok": True}
    assert lifecycle_calls == [tmp_path]


@pytest.mark.parametrize("language", ("en", "vi"))
def test_default_stop_confirmation_is_translated_warning_and_defaults_to_no(
    monkeypatch, language
):
    import tkinter.messagebox as messagebox
    import app.cli.desktop_ui as desktop_ui

    root = object()
    calls = []
    monkeypatch.setattr(
        messagebox,
        "askyesno",
        lambda *args, **kwargs: calls.append((args, kwargs)) or False,
    )

    translator = DesktopTranslator(language)

    assert desktop_ui.confirm_stop(root, translator) is False
    assert calls == [
        (
            (
                translator.text("dialog.stop_title"),
                translator.text("dialog.stop_body"),
            ),
            {"parent": root, "icon": "warning", "default": "no"},
        )
    ]


def test_legacy_tk_desktop_ui_starts_boot_before_dashboard_and_forwards_stop_dependencies(
    monkeypatch,
):
    import app.cli.desktop_ui as desktop_ui

    class Root:
        def __init__(self):
            self.mainloop_calls = 0

        def mainloop(self):
            self.mainloop_calls += 1

    class BootScreen:
        def close(self):
            raise AssertionError("boot screen should remain open during dashboard launch")

    captured = {}
    boot_calls = []
    launch_order = []
    root = Root()

    def dashboard(*_args, **kwargs):
        launch_order.append("dashboard")
        captured.update(kwargs)

    fake_tk = types.ModuleType("tkinter")
    fake_tk.Tk = lambda: root
    fake_tk.TclError = RuntimeError
    fake_tk.ttk = object()
    monkeypatch.setitem(sys.modules, "tkinter", fake_tk)
    monkeypatch.setattr(desktop_ui, "_DesktopDashboard", dashboard)

    def start_boot(received_root, received_tk):
        launch_order.append("boot")
        boot_calls.append((received_root, received_tk))
        return BootScreen()

    monkeypatch.setattr(
        desktop_ui,
        "_start_desktop_boot",
        start_boot,
    )
    stop_action = lambda _repo_root: {"ok": True}
    stop_confirmation = lambda _root, _translator: True

    assert (
        desktop_ui.run_tk_desktop_ui(
            object(),
            stop_action=stop_action,
            stop_confirmation=stop_confirmation,
        )
        == 0
    )
    assert captured["stop_action"] is stop_action
    assert captured["stop_confirmation"] is stop_confirmation
    assert boot_calls == [(root, fake_tk)]
    assert launch_order == ["boot", "dashboard"]
    assert root.mainloop_calls == 1


def test_legacy_tk_desktop_ui_boot_and_stop_launcher_cleans_up_dashboard_error(monkeypatch):
    import app.cli.desktop_ui as desktop_ui

    class Root:
        def __init__(self):
            self.destroy_calls = 0
            self.mainloop_calls = 0

        def destroy(self):
            launch_order.append("destroy")
            self.destroy_calls += 1

        def mainloop(self):
            self.mainloop_calls += 1

    class BootScreen:
        def __init__(self):
            self.close_calls = 0

        def close(self):
            launch_order.append("boot.close")
            self.close_calls += 1

    launch_order = []
    root = Root()
    boot_screen = BootScreen()
    fake_tk = types.ModuleType("tkinter")
    fake_tk.Tk = lambda: root
    fake_tk.TclError = RuntimeError
    fake_tk.ttk = object()
    monkeypatch.setitem(sys.modules, "tkinter", fake_tk)

    def start_boot(_received_root, _received_tk):
        launch_order.append("boot")
        return boot_screen

    monkeypatch.setattr(
        desktop_ui,
        "_start_desktop_boot",
        start_boot,
    )

    def failing_dashboard(*_args, **_kwargs):
        launch_order.append("dashboard")
        raise RuntimeError("dashboard initialization failed")

    monkeypatch.setattr(desktop_ui, "_DesktopDashboard", failing_dashboard)

    with pytest.raises(RuntimeError, match="dashboard initialization failed"):
        desktop_ui.run_tk_desktop_ui(object())

    assert launch_order == ["boot", "dashboard", "boot.close", "destroy"]
    assert boot_screen.close_calls == 1
    assert root.destroy_calls == 1
    assert root.mainloop_calls == 0


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
    dashboard.navigation_bindings = Bindings()
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
    assert dashboard.navigation_bindings.translators[-1].language == "vi"
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
