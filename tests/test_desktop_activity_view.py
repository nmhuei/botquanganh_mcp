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


def test_activity_compact_mode_auto_collapses_and_restores_session_rail(tmp_path):
    view = ActivityView(
        root=None,
        tk=None,
        ttk=None,
        parent=None,
        workspace_root=lambda: tmp_path,
        on_message=lambda *_args: None,
        on_refresh=lambda: None,
    )
    calls = []
    view.toggle_sessions_panel = lambda: (
        calls.append("toggle"),
        setattr(view, "sessions_collapsed", not view.sessions_collapsed),
    )

    view.set_compact(True)
    assert view.sessions_collapsed is True
    assert view.compact_auto_collapsed is True

    view.set_compact(False)
    assert view.sessions_collapsed is False
    assert view.compact_auto_collapsed is False
    assert calls == ["toggle", "toggle"]


def test_workspace_sessions_are_sorted_by_creation_time_not_recent_activity(tmp_path):
    older = tmp_path / "chat-older"
    newer = tmp_path / "chat-newer"
    older.mkdir()
    newer.mkdir()
    (older / "meta.json").write_text(
        '{"created_at":"2026-08-30T00:00:01+00:00"}',
        encoding="utf-8",
    )
    (newer / "meta.json").write_text(
        '{"created_at":"2026-08-30T00:00:02+00:00"}',
        encoding="utf-8",
    )
    # Recent activity in the older session must not move it below the newer one.
    (older / "journal.jsonl").write_text("recent activity\n", encoding="utf-8")

    sessions = discover_workspace_sessions(tmp_path)

    assert [session.chat_id for session in sessions] == ["chat-older", "chat-newer"]
    assert sessions[0].created_at < sessions[1].created_at


def test_new_activity_reveals_session_without_stealing_current_selection_or_filter(tmp_path):
    class Filter:
        def __init__(self, value):
            self.value = value

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
        on_message=lambda *_args: None,
        on_refresh=lambda: None,
    )
    view.sessions = [
        WorkspaceSession("chat-1", tmp_path / "chat-1", 10.0, 1.0),
        WorkspaceSession("chat-2", tmp_path / "chat-2", 20.0, 2.0),
    ]
    view.visible_session_ids = {"chat-1"}
    view.session_selected_id = "chat-1"
    view.workplace_filter_var = Filter("chat-1")

    assert view.reveal_session_for_activity("chat-2") is False

    assert view.session_selected_id == "chat-1"
    assert view.visible_session_ids == {"chat-1", "chat-2"}
    assert view.workplace_filter_var.get() == "chat-1"


def test_new_activity_selects_first_session_only_when_nothing_is_selected(tmp_path):
    view = ActivityView(
        root=None,
        tk=None,
        ttk=None,
        parent=None,
        workspace_root=lambda: tmp_path,
        on_message=lambda *_args: None,
        on_refresh=lambda: None,
    )

    assert view.reveal_session_for_activity("chat-1") is True
    assert view.session_selected_id == "chat-1"
    assert view.visible_session_ids == {"chat-1"}
