from app.cli.desktop_views.activity import (
    ActivityView,
    WorkspaceSession,
    activity_status_label,
    clip_text,
    command_activity_human_output,
    command_activity_inspector_content,
    command_activity_metadata,
    discover_workspace_sessions,
    format_stream_time,
    filter_activity_records_for_session,
    project_command_activity_records,
)
from app.cli.desktop_views.i18n import DesktopTranslator


def test_activity_view_models_workplace_sessions_and_filters_records(tmp_path):
    (tmp_path / "chat-a").mkdir()
    (tmp_path / "chat-b").mkdir()
    (tmp_path / ".archive" / "old-chat").mkdir(parents=True)

    sessions = discover_workspace_sessions(tmp_path)
    records = [
        {"event_id": "one", "chat_id": "chat-a", "command": "pwd"},
        {"event_id": "two", "chat_id": "chat-b", "command": "ls"},
    ]

    assert {session.chat_id for session in sessions} == {"chat-a", "chat-b"}
    assert all(isinstance(session, WorkspaceSession) for session in sessions)
    assert filter_activity_records_for_session(records, "chat-a") == [records[0]]


def test_activity_view_refresh_combines_snapshots_and_reports_new_activity(tmp_path):
    view = ActivityView(
        root=None,
        tk=None,
        ttk=None,
        parent=None,
        workspace_root=lambda: tmp_path,
        on_message=lambda _kind, _message: None,
        on_refresh=lambda: None,
    )
    session = WorkspaceSession("chat-a", tmp_path / "chat-a", 1.0)
    record = {"event_id": "event-a", "chat_id": "chat-a", "command": "pwd"}

    assert view.refresh([session], [record]) == set()
    assert view.sessions == [session]
    assert view.records[0]["event_id"] == "event-a"
    assert view.records[0]["activity_status"] == "failed"
    assert view.refresh([session], [record]) == set()


def test_activity_view_starts_empty_then_reveals_a_session_for_new_command(tmp_path):
    """A startup history snapshot must not open host-chat folders in the rail."""
    view = ActivityView(
        root=None,
        tk=None,
        ttk=None,
        parent=None,
        workspace_root=lambda: tmp_path,
        on_message=lambda _kind, _message: None,
        on_refresh=lambda: None,
    )
    session = WorkspaceSession("chat-a", tmp_path / "chat-a", 1.0)
    historic = {"event_id": "historic", "chat_id": "chat-a", "command": "pwd"}
    new_command = {"event_id": "new", "chat_id": "chat-a", "command": "whoami"}

    assert view.refresh([session], [historic]) == set()
    assert view.visible_session_ids == set()

    notifications = view.refresh([session], [historic, new_command])
    assert {(notice.chat_id, notice.operation_id) for notice in notifications} == {
        ("chat-a", "new")
    }
    assert view.activate_session("chat-a") is True
    assert view.visible_session_ids == {"chat-a"}


def test_activity_view_keeps_existing_session_positions_when_activity_updates_time(tmp_path):
    view = ActivityView(
        root=None,
        tk=None,
        ttk=None,
        parent=None,
        workspace_root=lambda: tmp_path,
        on_message=lambda _kind, _message: None,
        on_refresh=lambda: None,
    )
    older_running_session = WorkspaceSession("chat-a", tmp_path / "chat-a", 1.0)
    newer_idle_session = WorkspaceSession("chat-b", tmp_path / "chat-b", 2.0)

    view.refresh([newer_idle_session, older_running_session], [])
    refreshed_running_session = WorkspaceSession("chat-a", tmp_path / "chat-a", 3.0)
    view.refresh(
        [refreshed_running_session, newer_idle_session],
        [
            {
                "event_id": "event-a",
                "chat_id": "chat-a",
                "operation_id": "operation-a",
                "phase": "started",
                "status": "running",
            }
        ],
    )

    assert [session.chat_id for session in view.sessions] == ["chat-b", "chat-a"]


def test_activity_view_treats_command_lifecycle_as_one_popup_candidate(tmp_path):
    """A completed event must not re-alert for a command already seen running."""
    view = ActivityView(
        root=None,
        tk=None,
        ttk=None,
        parent=None,
        workspace_root=lambda: tmp_path,
        on_message=lambda _kind, _message: None,
        on_refresh=lambda: None,
    )
    session = WorkspaceSession("chat-a", tmp_path / "chat-a", 1.0)
    started = {
        "event_id": "start-1",
        "operation_id": "command-1",
        "phase": "started",
        "status": "running",
        "chat_id": "chat-a",
        "command": "sleep 1",
    }
    completed = {
        "event_id": "done-1",
        "operation_id": "command-1",
        "phase": "completed",
        "status": "succeeded",
        "chat_id": "chat-a",
        "command": "sleep 1",
        "ok": True,
    }

    assert view.refresh([], []) == set()
    notifications = view.refresh([session], [started])
    assert {(notice.chat_id, notice.operation_id) for notice in notifications} == {
        ("chat-a", "command-1")
    }
    assert view.refresh([session], [started, completed]) == set()


def test_activity_view_auto_activation_clears_a_session_filter_that_hides_the_new_chat(tmp_path):
    class Filter:
        def __init__(self):
            self.value = "other-chat"

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    view = ActivityView(
        root=None,
        tk=None,
        ttk=None,
        parent=None,
        workspace_root=lambda: tmp_path,
        on_message=lambda _kind, _message: None,
        on_refresh=lambda: None,
    )
    view.workplace_filter_var = Filter()

    assert view.activate_session("chat-a") is True
    assert view.workplace_filter_var.get() == ""


def test_activity_language_change_preserves_record_and_running_session(tmp_path):
    view = ActivityView(
        root=None,
        tk=None,
        ttk=None,
        parent=None,
        workspace_root=lambda: tmp_path,
        on_message=lambda _kind, _message: None,
        on_refresh=lambda: None,
        translator=DesktopTranslator("en"),
    )
    session = WorkspaceSession("chat-a", tmp_path / "chat-a", 1.0)
    record = {
        "event_id": "evt",
        "chat_id": "chat-a",
        "operation_id": "act",
        "phase": "started",
        "status": "running",
    }

    view.refresh([session], [record])
    view.set_translator(DesktopTranslator("vi"))

    assert view.records[0]["event_id"] == "evt"
    assert view.running_session_ids == {"chat-a"}


def test_activity_projection_collapses_lifecycle_to_one_terminal_row():
    started = {
        "event_id": "start-1",
        "timestamp": "2026-08-28T01:00:00+00:00",
        "operation_id": "act-1",
        "phase": "started",
        "status": "running",
        "chat_id": "chat-a",
        "command": "sleep 10",
    }
    completed = {
        "event_id": "done-1",
        "timestamp": "2026-08-28T01:00:10+00:00",
        "operation_id": "act-1",
        "phase": "completed",
        "status": "succeeded",
        "chat_id": "chat-a",
        "command": "sleep 10",
        "ok": True,
        "stdout": "done",
    }

    projected = project_command_activity_records([completed, started])

    assert len(projected) == 1
    assert projected[0]["event_id"] == "done-1"
    assert projected[0]["activity_status"] == "succeeded"
    assert projected[0]["is_running"] is False
    assert projected[0]["stdout"] == "done"


def test_activity_view_exposes_running_workplace_from_started_event(tmp_path):
    view = ActivityView(
        root=None,
        tk=None,
        ttk=None,
        parent=None,
        workspace_root=lambda: tmp_path,
        on_message=lambda _kind, _message: None,
        on_refresh=lambda: None,
    )
    session = WorkspaceSession("chat-a", tmp_path / "chat-a", 1.0)
    started = {
        "event_id": "start-1",
        "operation_id": "act-1",
        "phase": "started",
        "status": "running",
        "chat_id": "chat-a",
        "command": "sleep 10",
    }

    assert view.refresh([session], [started]) == set()
    assert view.records[0]["is_running"] is True
    assert view.running_session_ids == {"chat-a"}


def test_activity_view_reopens_closed_session_once(tmp_path):
    view = ActivityView(
        root=None,
        tk=None,
        ttk=None,
        parent=None,
        workspace_root=lambda: tmp_path,
        on_message=lambda _kind, _message: None,
        on_refresh=lambda: None,
    )
    view.closed_session_ids.add("chat-a")

    assert view.reopen_session("chat-a") is True
    assert view.reopen_session("chat-a") is False
    assert view.session_selected_id == "chat-a"


def test_activity_view_focuses_only_after_a_real_closed_tab_reopens(tmp_path):
    calls = []

    class Root:
        def deiconify(self):
            calls.append("deiconify")

        def lift(self):
            calls.append("lift")

    class Notebook:
        def select(self, tab):
            calls.append(("select", tab))

    view = ActivityView(
        root=Root(),
        tk=type("Tk", (), {"TclError": RuntimeError}),
        ttk=None,
        parent=None,
        workspace_root=lambda: tmp_path,
        on_message=lambda _kind, _message: None,
        on_refresh=lambda: None,
    )
    view.set_activity_tab(Notebook(), "gpt-tab")
    view.closed_session_ids.add("chat-a")

    assert view.reopen_session("chat-a") is True
    view.focus()

    assert calls == [("select", "gpt-tab"), "deiconify", "lift"]


def test_activity_view_refresh_renders_each_snapshot_once(tmp_path):
    view = ActivityView(
        root=None,
        tk=None,
        ttk=None,
        parent=None,
        workspace_root=lambda: tmp_path,
        on_message=lambda _kind, _message: None,
        on_refresh=lambda: None,
    )
    calls = []
    view._render_sessions = lambda: calls.append("sessions")
    view._render_records = lambda: calls.append("records")

    view.refresh([], [])

    assert calls == ["sessions", "records"]


def test_activity_helpers_keep_command_input_and_output_separate():
    record = {
        "event_id": "evt-1",
        "chat_id": "chat-a",
        "command": "printf hello",
        "ok": True,
        "stdout": "hello\n",
        "stderr": "",
    }

    assert clip_text("  a\n b\t c  ", 20) == "a b c"
    assert format_stream_time("not-a-time") == "—"
    assert '"stdout"' in command_activity_metadata(record)
    assert "STDOUT\nhello" in command_activity_human_output(record)
    assert "STDERR\n(empty)" in command_activity_human_output(record)
    vietnamese_output = command_activity_human_output(record, DesktopTranslator("vi"))
    assert "Trạng thái: XONG" in vietnamese_output
    assert "Kết quả: thành công" in vietnamese_output
    assert command_activity_inspector_content(record) == {
        "metadata": command_activity_metadata(record),
        "stdout": "hello\n",
        "stderr": "(empty)",
        "human": command_activity_human_output(record),
    }


def test_activity_status_labels_are_explicit_for_every_lifecycle_outcome():
    translator = DesktopTranslator("vi")

    assert activity_status_label("running", translator) == "ĐANG CHẠY"
    assert activity_status_label("succeeded", translator) == "XONG"
    assert activity_status_label("failed", translator) == "LỖI"
    assert activity_status_label("timed_out", translator) == "HẾT THỜI GIAN"


def test_activity_view_collapse_controls_preserve_splitter_membership():
    class Panel:
        pass

    class Panes:
        def __init__(self):
            self.calls = []

        def forget(self, panel):
            self.calls.append(("forget", panel))

        def insert(self, index, panel, **_kwargs):
            self.calls.append(("insert", index, panel))

        def add(self, panel, **_kwargs):
            self.calls.append(("add", panel))

    class Button:
        def configure(self, **_kwargs):
            pass

    view = ActivityView(
        root=None,
        tk=None,
        ttk=None,
        parent=None,
        workspace_root=lambda: tmp_path,
        on_message=lambda _kind, _message: None,
        on_refresh=lambda: None,
    )
    inputs, output = Panel(), Panel()
    panes = Panes()
    view.input_panel = inputs
    view.output_panel = output
    view.activity_vertical_panes = panes
    view.input_collapse_button = Button()
    view.output_collapse_button = Button()

    view.toggle_input_panel()
    view.toggle_output_panel()
    view.toggle_input_panel()
    view.toggle_output_panel()

    assert panes.calls == [
        ("forget", inputs),
        ("forget", output),
        ("insert", 0, inputs),
        ("add", output),
    ]


def test_activity_view_builds_premium_controls_without_breaking_local_callbacks(tmp_path):
    """Dropping a shared activity style or local control callback is a regression."""
    class Variable:
        def __init__(self, value=""):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    class Widget:
        def __init__(self, parent=None, **kwargs):
            self.parent = parent
            self.options = dict(kwargs)
            self.bindings = {}

        def bind(self, sequence, callback):
            self.bindings[sequence] = callback

        def configure(self, **kwargs):
            self.options.update(kwargs)

        def grid(self, **_kwargs):
            pass

        def pack(self, **_kwargs):
            pass

        def columnconfigure(self, *_args, **_kwargs):
            pass

        def rowconfigure(self, *_args, **_kwargs):
            pass

        def yview(self, *_args):
            return (0.0, 1.0)

        def xview(self, *_args):
            return (0.0, 1.0)

        def yview_moveto(self, _position):
            pass

        def set(self, *_args):
            pass

        def focus_set(self):
            pass

    class Tree(Widget):
        def heading(self, *_args, **_kwargs):
            pass

        def column(self, *_args, **_kwargs):
            pass

        def tag_configure(self, *_args, **_kwargs):
            pass

        def get_children(self):
            return ()

        def delete(self, _item):
            pass

        def insert(self, *_args, **_kwargs):
            pass

        def selection(self):
            return ()

        def selection_set(self, _item):
            pass

        def see(self, _item):
            pass

    class Panedwindow(Widget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.pane_calls = []

        def add(self, panel, **kwargs):
            self.pane_calls.append(("add", panel, kwargs))

        def forget(self, panel):
            self.pane_calls.append(("forget", panel, {}))

        def insert(self, index, panel, **kwargs):
            self.pane_calls.append(("insert", index, panel, kwargs))

    class Notebook(Widget):
        def add(self, _frame, **_kwargs):
            pass

        def select(self):
            return ""

        def tab(self, _frame, **_kwargs):
            pass

    class Text(Widget):
        def get(self, *_args):
            return ""

    class Root:
        def __init__(self):
            self.bindings = {}
            self.after_calls = []
            self.cancelled_jobs = []

        def bind(self, sequence, callback):
            self.bindings[sequence] = callback

        def after(self, delay, callback):
            self.after_calls.append((delay, callback))
            return len(self.after_calls)

        def after_cancel(self, job):
            self.cancelled_jobs.append(job)

    class Ttk:
        def __init__(self):
            self.widgets = []
            self.label_frame_styles = []
            self.entry_styles = []
            self.tree_styles = []
            self.button_styles = []
            self.notebook_styles = []

        def _widget(self, kind, args, kwargs, widget_type=Widget):
            widget = widget_type(args[0] if args else None, **kwargs)
            widget.kind = kind
            self.widgets.append(widget)
            return widget

        def Frame(self, *args, **kwargs):
            return self._widget("Frame", args, kwargs)

        def Label(self, *args, **kwargs):
            return self._widget("Label", args, kwargs)

        def LabelFrame(self, *args, **kwargs):
            widget = self._widget("LabelFrame", args, kwargs)
            self.label_frame_styles.append(widget.options.get("style"))
            return widget

        def Button(self, *args, **kwargs):
            widget = self._widget("Button", args, kwargs)
            self.button_styles.append(widget.options.get("style"))
            return widget

        def Entry(self, *args, **kwargs):
            widget = self._widget("Entry", args, kwargs)
            self.entry_styles.append(widget.options.get("style"))
            return widget

        def Panedwindow(self, *args, **kwargs):
            return self._widget("Panedwindow", args, kwargs, Panedwindow)

        def Treeview(self, *args, **kwargs):
            widget = self._widget("Treeview", args, kwargs, Tree)
            self.tree_styles.append(widget.options.get("style"))
            return widget

        def Scrollbar(self, *args, **kwargs):
            return self._widget("Scrollbar", args, kwargs)

        def Notebook(self, *args, **kwargs):
            widget = self._widget("Notebook", args, kwargs, Notebook)
            self.notebook_styles.append(widget.options.get("style"))
            return widget

    root = Root()
    ttk = Ttk()
    view = ActivityView(
        root=root,
        tk=type("Tk", (), {"StringVar": Variable, "Text": Text, "TclError": RuntimeError}),
        ttk=ttk,
        parent=Widget(),
        workspace_root=lambda: tmp_path,
        on_message=lambda _kind, _message: None,
        on_refresh=lambda: None,
    )

    assert ttk.label_frame_styles == [
        "RailPanel.TLabelframe",
        "InspectorCard.TLabelframe",
        "InspectorCard.TLabelframe",
    ]
    assert ttk.entry_styles == ["Filter.TEntry", "Filter.TEntry"]
    assert ttk.tree_styles == ["Table.Treeview", "Table.Treeview"]
    assert ttk.notebook_styles == ["Inspector.TNotebook"]
    assert "SectionHeader.TLabel" in [
        widget.options.get("style") for widget in ttk.widgets if widget.kind == "Label"
    ]
    assert set(ttk.button_styles) == {"Secondary.TButton"}
    assert view.input_collapse_button is not None
    assert view.output_collapse_button is not None

    view.workplace_filter_entry.bindings["<KeyRelease>"](object())
    view.command_filter_entry.bindings["<KeyRelease>"](object())
    view.input_collapse_button.options["command"]()
    view.output_collapse_button.options["command"]()

    assert [delay for delay, _callback in root.after_calls] == [120, 120]
    assert root.cancelled_jobs == [1]
    assert ("forget", view.input_panel, {}) in view.activity_vertical_panes.pane_calls
    assert ("forget", view.output_panel, {}) in view.activity_vertical_panes.pane_calls
