import os

import pytest


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def test_qt_activity_state_starts_empty_then_reveals_new_command(tmp_path):
    """A post-baseline command must create exactly one revealable notice."""
    from app.cli.desktop_qt.activity import ActivityState
    from app.cli.desktop_views.activity import WorkspaceSession

    state = ActivityState(workspace_root=lambda: tmp_path)
    session = WorkspaceSession("chat-a", tmp_path / "chat-a", 1.0)
    historic = {"event_id": "historic", "chat_id": "chat-a", "command": "pwd"}
    live = {"event_id": "live", "chat_id": "chat-a", "command": "whoami"}

    assert state.refresh([session], [historic]) == set()
    assert state.visible_session_ids == set()
    notices = state.refresh([session], [historic, live])

    assert [(notice.chat_id, notice.operation_id) for notice in notices] == [("chat-a", "live")]
    assert state.reveal_session("chat-a") is True
    assert state.visible_session_ids == {"chat-a"}


def test_qt_activity_command_model_collapses_lifecycle(qapp, tmp_path):
    """A completed lifecycle row is displayed once, rather than as start and end."""
    from PySide6 import QtCore
    from app.cli.desktop_qt.activity import ActivityCommandModel, ActivityState

    state = ActivityState(workspace_root=lambda: tmp_path)
    state.records = [
        {
            "event_id": "done",
            "chat_id": "chat-a",
            "command": "sleep 1",
            "activity_status": "succeeded",
            "ok": True,
        }
    ]
    model = ActivityCommandModel(QtCore, state)

    assert model.rowCount() == 1
    assert model.data(model.index(0, 3), QtCore.Qt.DisplayRole) == "sleep 1"


def test_qt_activity_panel_exposes_the_investigation_workbench_layout(qapp, tmp_path):
    """Removing the named investigation regions would break the activity workbench."""
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.activity import QtActivityPanel

    panel = QtActivityPanel(QtCore, QtWidgets, workspace_root=lambda: tmp_path)

    assert panel.session_rail.objectName() == "activitySessionRail"
    assert panel.session_rail.minimumWidth() == 260
    assert panel.command_toolbar.objectName() == "activityCommandToolbar"
    assert panel.command_frame.objectName() == "activityCommandFrame"
    assert panel.investigation_splitter.objectName() == "activityInvestigationSplitter"
    assert panel.investigation_splitter.orientation() == QtCore.Qt.Horizontal
    assert panel.inspector_frame.objectName() == "inspectorSurface"
    assert panel.input_collapse_button.focusPolicy() != QtCore.Qt.NoFocus
    assert panel.output_collapse_button.focusPolicy() != QtCore.Qt.NoFocus


def test_qt_activity_workbench_uses_free_nested_splitters(qapp, tmp_path):
    """Session rail, command history, and inspector frame remain user-resizable work surfaces."""
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.activity import QtActivityPanel

    panel = QtActivityPanel(QtCore, QtWidgets, workspace_root=lambda: tmp_path)
    panel.widget.resize(1000, 700)
    panel.widget.show()
    qapp.processEvents()

    assert panel.activity_workbench_splitter.orientation() == QtCore.Qt.Horizontal
    assert panel.activity_workbench_splitter.indexOf(panel.session_rail) == 0
    assert panel.activity_workbench_splitter.indexOf(panel.command_frame) == 1
    assert panel.activity_workbench_splitter.indexOf(panel.inspection_workspace) == 2

    panel.activity_workbench_splitter.setSizes((260, 340, 400))
    qapp.processEvents()
    outer_sizes = panel.activity_workbench_splitter.sizes()

    assert outer_sizes[2] > outer_sizes[0]

    panel.render()
    qapp.processEvents()

    assert (
        panel.activity_workbench_splitter.sizes()[2]
        > panel.activity_workbench_splitter.sizes()[0]
    )


def test_qt_activity_session_model_exposes_complete_cell_tooltips(qapp, tmp_path):
    """An elided session row must retain every complete value for users."""
    from PySide6 import QtCore
    from app.cli.desktop_qt.activity import ActivitySessionModel, ActivityState
    from app.cli.desktop_views.activity import WorkspaceSession

    state = ActivityState(workspace_root=lambda: tmp_path)
    state.refresh(
        [WorkspaceSession("incident-retrospective", tmp_path / "session", 10.0)],
        [],
    )
    state.reveal_session("incident-retrospective")
    model = ActivitySessionModel(QtCore, state)

    assert model.columnCount() == 1
    assert model.data(model.index(0, 0), QtCore.Qt.ToolTipRole) == "incident-retrospective"
    assert model.data(model.index(0, 0), QtCore.Qt.DisplayRole) == "incident-retrospective"


def test_qt_activity_workbench_headings_follow_the_active_translator(qapp, tmp_path):
    """The new workbench regions must not retain English after switching language."""
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.activity import QtActivityPanel
    from app.cli.desktop_views.i18n import DesktopTranslator

    panel = QtActivityPanel(QtCore, QtWidgets, workspace_root=lambda: tmp_path)
    translator = DesktopTranslator("vi")
    panel.set_translator(translator)

    assert panel.session_heading.text() == translator.text("activity.workplaces")
    assert panel.session_source.text() == translator.text("activity.folder_source")
    assert panel.command_heading.text() == translator.text("activity.commands")
    assert panel.inspector_heading.text() == translator.text("activity.output")
    panel.toggle_input_panel()
    panel.set_translator(translator)
    assert panel.input_toggle.text() == "▸ Mở rộng Đầu vào"
    assert panel.input_toggle.accessibleName() == "Mở rộng Đầu vào"
    assert panel.input_toggle.toolTip() == "Mở rộng Đầu vào"


def test_qt_activity_panel_sorts_commands_when_a_header_is_clicked(qapp, tmp_path):
    """A command-table header click changes the local sort and rendered row order."""
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.activity import QtActivityPanel

    panel = QtActivityPanel(QtCore, QtWidgets, workspace_root=lambda: tmp_path)
    panel.state.records = [
        {"event_id": "first", "command": "zulu", "activity_status": "succeeded"},
        {"event_id": "second", "command": "alpha", "activity_status": "succeeded"},
    ]

    panel.command_table.horizontalHeader().sectionClicked.emit(3)

    assert panel.state.sort_key == "command"
    assert panel.command_model.data(
        panel.command_model.index(0, 3), QtCore.Qt.DisplayRole
    ) == "alpha"


def test_qt_activity_panel_shortcuts_work_while_a_child_has_focus(qapp, tmp_path):
    """Slash and Escape remain panel commands while the command table owns focus."""
    from PySide6 import QtCore, QtTest, QtWidgets
    from app.cli.desktop_qt.activity import QtActivityPanel

    panel = QtActivityPanel(QtCore, QtWidgets, workspace_root=lambda: tmp_path)
    panel.widget.show()
    qapp.processEvents()
    panel.command_table.setFocus()
    QtTest.QTest.keyClick(panel.command_table, QtCore.Qt.Key_Slash)

    assert panel.command_filter_input.hasFocus()
    panel.workplace_filter_input.setText("chat-a")
    panel.command_filter_input.setText("pwd")
    panel.command_table.setFocus()
    QtTest.QTest.keyClick(panel.command_table, QtCore.Qt.Key_Escape)

    assert panel.state.workplace_filter == ""
    assert panel.state.command_filter == ""


def test_qt_activity_refresh_preserves_selected_event_scroll_and_inspector(qapp, tmp_path):
    """Refresh keeps the selected command, its inspector, and the table viewport."""
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.activity import QtActivityPanel

    panel = QtActivityPanel(QtCore, QtWidgets, workspace_root=lambda: tmp_path)
    panel.widget.resize(1000, 700)
    panel.widget.show()
    records = [
        {
            "event_id": f"event-{index}",
            "command": f"command-{index}",
            "activity_status": "succeeded",
            "stdout": f"output-{index}",
        }
        for index in range(40)
    ]
    panel.refresh([], records)
    panel.command_table.selectRow(20)
    qapp.processEvents()
    scroll_bar = panel.command_table.verticalScrollBar()
    scroll_bar.setValue(7)
    before_scroll = scroll_bar.value()

    records[20] = {
        "event_id": "event-20",
        "command": "command-20-updated",
        "activity_status": "succeeded",
        "stdout": "preserved-inspector-output",
    }
    panel.refresh([], records)
    qapp.processEvents()

    selected = panel.command_table.currentIndex()
    assert selected.isValid()
    assert panel.state.filtered_records()[selected.row()]["event_id"] == "event-20"
    assert scroll_bar.value() == before_scroll
    assert panel.inspector_views["stdout"].toPlainText() == "preserved-inspector-output"


def test_qt_activity_input_and_output_wrap_long_tokens_after_splitter_resize(
    qapp, tmp_path
):
    """Narrow inspectors wrap every long token instead of clipping it sideways."""
    from PySide6 import QtCore, QtGui, QtWidgets
    from app.cli.desktop_qt.activity import QtActivityPanel

    panel = QtActivityPanel(QtCore, QtWidgets, workspace_root=lambda: tmp_path)
    panel.widget.resize(1000, 700)
    panel.widget.show()
    long_line = "x" * 480
    long_text = "\n".join(f"{long_line}-{index}" for index in range(80))
    record = {
        "event_id": "long-command",
        "command": long_text,
        "activity_status": "succeeded",
        "stdout": long_text,
    }
    panel.refresh([], [record])
    panel.command_table.selectRow(0)
    panel.inspector.setCurrentWidget(panel.inspector_views["stdout"])
    panel.content_splitter.setSizes((260, 560, 180))
    qapp.processEvents()

    input_view = panel.command_input_view
    output_view = panel.inspector_views["stdout"]
    assert output_view.viewport().width() < 250
    for view in (input_view, *panel.inspector_views.values()):
        assert view.lineWrapMode() == QtWidgets.QPlainTextEdit.WidgetWidth
        assert view.wordWrapMode() == QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere
        assert view.horizontalScrollBarPolicy() == QtCore.Qt.ScrollBarAlwaysOff
    assert input_view.toPlainText() == long_text
    assert output_view.toPlainText() == long_text
    assert input_view.horizontalScrollBar().maximum() == 0
    assert output_view.horizontalScrollBar().maximum() == 0
    assert input_view.verticalScrollBar().maximum() > input_view.verticalScrollBar().minimum()
    assert output_view.verticalScrollBar().maximum() > output_view.verticalScrollBar().minimum()


def test_qt_activity_vertical_scrollbars_survive_same_record_refresh(qapp, tmp_path):
    """Wrapped long code/content keeps its vertical viewport across refreshes."""
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.activity import QtActivityPanel

    panel = QtActivityPanel(QtCore, QtWidgets, workspace_root=lambda: tmp_path)
    panel.widget.resize(1000, 700)
    panel.widget.show()
    long_line = "x" * 480
    long_text = "\n".join(f"{long_line}-{index}" for index in range(80))
    record = {
        "event_id": "long-command",
        "command": long_text,
        "activity_status": "succeeded",
        "stdout": long_text,
    }
    panel.refresh([], [record])
    panel.command_table.selectRow(0)
    panel.inspector.setCurrentWidget(panel.inspector_views["stdout"])
    qapp.processEvents()

    input_view = panel.command_input_view
    output_view = panel.inspector_views["stdout"]
    scroll_bars = (
        input_view.verticalScrollBar(),
        output_view.verticalScrollBar(),
    )
    assert all(scroll_bar.maximum() > scroll_bar.minimum() for scroll_bar in scroll_bars)
    for scroll_bar in scroll_bars:
        scroll_bar.setValue(min(scroll_bar.minimum() + 8, scroll_bar.maximum()))
    before_positions = tuple(scroll_bar.value() for scroll_bar in scroll_bars)

    panel.refresh([], [record])
    qapp.processEvents()

    assert tuple(scroll_bar.value() for scroll_bar in scroll_bars) == before_positions


def test_qt_activity_changed_same_record_keeps_editor_scroll_across_queued_refreshes(
    qapp, tmp_path, monkeypatch
):
    """Consecutive same-command refreshes retain the viewport before Qt drains."""
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.activity import QtActivityPanel

    panel = QtActivityPanel(QtCore, QtWidgets, workspace_root=lambda: tmp_path)
    panel.widget.resize(1000, 700)
    panel.widget.show()
    long_line = "x" * 480
    long_text = "\n".join(f"{long_line}-{index}" for index in range(80))
    original = {
        "event_id": "long-command",
        "command": long_text,
        "activity_status": "succeeded",
        "stdout": long_text,
    }
    panel.refresh([], [original])
    panel.command_table.selectRow(0)
    panel.inspector.setCurrentWidget(panel.inspector_views["stdout"])
    qapp.processEvents()

    scroll_bars = (
        panel.command_input_view.verticalScrollBar(),
        panel.inspector_views["stdout"].verticalScrollBar(),
    )
    for scroll_bar in scroll_bars:
        scroll_bar.setValue(min(scroll_bar.minimum() + 8, scroll_bar.maximum()))
    expected_positions = tuple(scroll_bar.value() for scroll_bar in scroll_bars)
    assert all(position > 0 for position in expected_positions)

    callbacks = []
    monkeypatch.setattr(
        QtCore.QTimer,
        "singleShot",
        staticmethod(lambda _delay, callback: callbacks.append(callback)),
    )
    first_update = {**original, "command": f"{long_text}-first", "stdout": f"{long_text}-first"}
    second_update = {**original, "command": f"{long_text}-second", "stdout": f"{long_text}-second"}

    panel.refresh([], [first_update])
    panel.refresh([], [second_update])
    for callback in reversed(callbacks):
        callback()

    assert tuple(scroll_bar.value() for scroll_bar in scroll_bars) == expected_positions


def test_qt_activity_new_command_opens_editors_at_the_start(qapp, tmp_path):
    """Selecting a different command must not inherit the old command viewport."""
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.activity import QtActivityPanel

    panel = QtActivityPanel(QtCore, QtWidgets, workspace_root=lambda: tmp_path)
    panel.widget.resize(1000, 700)
    panel.widget.show()
    long_line = "x" * 480
    long_text = "\n".join(f"{long_line}-{index}" for index in range(80))
    records = [
        {
            "event_id": "first-command",
            "command": long_text,
            "activity_status": "succeeded",
            "stdout": long_text,
        },
        {
            "event_id": "second-command",
            "command": f"second-{long_text}",
            "activity_status": "succeeded",
            "stdout": f"second-{long_text}",
        },
    ]
    panel.refresh([], records)
    panel.command_table.selectRow(0)
    panel.inspector.setCurrentWidget(panel.inspector_views["stdout"])
    qapp.processEvents()

    scroll_bars = (
        panel.command_input_view.verticalScrollBar(),
        panel.inspector_views["stdout"].verticalScrollBar(),
    )
    for scroll_bar in scroll_bars:
        scroll_bar.setValue(min(scroll_bar.minimum() + 8, scroll_bar.maximum()))
    assert all(scroll_bar.value() > 0 for scroll_bar in scroll_bars)

    panel.command_table.selectRow(1)
    qapp.processEvents()

    assert all(scroll_bar.value() == scroll_bar.minimum() for scroll_bar in scroll_bars)


def test_qt_activity_same_content_selection_keeps_pending_scroll_restore(
    qapp, tmp_path, monkeypatch
):
    """A repeated selection must not cancel its prior deferred editor restore."""
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.activity import QtActivityPanel

    panel = QtActivityPanel(QtCore, QtWidgets, workspace_root=lambda: tmp_path)
    panel.widget.resize(1000, 700)
    panel.widget.show()
    long_text = "\n".join(f"{'x' * 480}-{index}" for index in range(80))
    original = {
        "event_id": "long-command",
        "command": long_text,
        "activity_status": "succeeded",
    }
    panel.refresh([], [original])
    panel.command_table.selectRow(0)
    qapp.processEvents()

    scroll_bar = panel.command_input_view.verticalScrollBar()
    scroll_bar.setValue(min(scroll_bar.minimum() + 8, scroll_bar.maximum()))
    expected_position = scroll_bar.value()
    assert expected_position > 0

    callbacks = []
    monkeypatch.setattr(
        QtCore.QTimer,
        "singleShot",
        staticmethod(lambda _delay, callback: callbacks.append(callback)),
    )
    panel.refresh([], [{**original, "command": f"{long_text}-updated"}])
    panel._show_selected_command()
    for callback in reversed(callbacks):
        callback()

    assert scroll_bar.value() == expected_position


def test_qt_activity_refresh_restores_viewport_after_deferred_table_layout(qapp, tmp_path):
    """A refresh must restore the command viewport after Qt's queued layout settles."""
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.activity import QtActivityPanel

    panel = QtActivityPanel(QtCore, QtWidgets, workspace_root=lambda: tmp_path)
    panel.widget.resize(1000, 700)
    panel.widget.show()
    records = [
        {
            "event_id": f"event-{index}",
            "command": f"command-{index}",
            "activity_status": "succeeded",
        }
        for index in range(40)
    ]
    panel.refresh([], records)
    panel.command_table.selectRow(20)
    qapp.processEvents()
    scroll_bar = panel.command_table.verticalScrollBar()
    scroll_bar.setValue(7)
    before_scroll = scroll_bar.value()
    assert before_scroll > scroll_bar.minimum()

    # QTableView can queue its own viewport correction after a model layout.
    # Queue the correction before refresh, as its layout path does, then require
    # the panel's restore to run after that correction rather than flicker to 0.
    QtCore.QTimer.singleShot(0, lambda: scroll_bar.setValue(scroll_bar.minimum()))
    panel.refresh([], records)
    qapp.processEvents()

    assert scroll_bar.value() == before_scroll


def test_qt_activity_latest_deferred_scroll_restore_wins_over_stale_callback(
    qapp, tmp_path, monkeypatch
):
    """Rapid renders must not let an older queued restore overwrite the viewport."""
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.activity import QtActivityPanel

    panel = QtActivityPanel(QtCore, QtWidgets, workspace_root=lambda: tmp_path)
    panel.widget.resize(1000, 700)
    panel.widget.show()
    records = [
        {
            "event_id": f"event-{index}",
            "command": f"command-{index}",
            "activity_status": "succeeded",
        }
        for index in range(40)
    ]
    panel.refresh([], records)
    panel.command_table.selectRow(20)
    qapp.processEvents()
    scroll_bar = panel.command_table.verticalScrollBar()
    callbacks = []
    monkeypatch.setattr(
        QtCore.QTimer,
        "singleShot",
        staticmethod(lambda _delay, callback: callbacks.append(callback)),
    )

    scroll_bar.setValue(7)
    panel.render()
    scroll_bar.setValue(12)
    newest_scroll = scroll_bar.value()
    panel.render()
    assert len(callbacks) == 2

    callbacks[1]()
    callbacks[0]()

    assert scroll_bar.value() == newest_scroll


def test_qt_activity_visible_collapse_controls_restore_from_shared_baseline(qapp, tmp_path):
    """The collapse control bar is removed from the visible layout so input/output remain large and open."""
    from PySide6 import QtCore, QtTest, QtWidgets
    from app.cli.desktop_qt.activity import QtActivityPanel

    panel = QtActivityPanel(QtCore, QtWidgets, workspace_root=lambda: tmp_path)
    panel.widget.resize(1000, 700)
    panel.widget.show()
    panel.widget.activateWindow()
    qapp.processEvents()

    # Collapse bar is removed/hidden from the visible workbench layout
    assert panel.investigation_controls.isVisibleTo(panel.widget) is False
    assert panel.input_panel.isVisible() is True
    assert panel.output_panel.isVisible() is True

    # Programmatic toggles still exist for backward compatibility
    panel.toggle_input_panel()
    assert panel.input_collapsed is True
    assert panel.input_panel.isVisible() is False
    assert panel.output_collapsed is False

    panel.toggle_input_panel()
    assert panel.input_collapsed is False
    assert panel.input_panel.isVisible() is True


def test_qt_activity_output_is_not_truncated(qapp, tmp_path):
    """Activity output must be full and untruncated without any truncation notices."""
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.activity import QtActivityPanel

    panel = QtActivityPanel(QtCore, QtWidgets, workspace_root=lambda: tmp_path)
    panel.widget.resize(1000, 700)
    panel.widget.show()

    # Create a large output record (>12000 chars)
    huge_stdout = "LINE " + "A" * 500 + "\n"
    huge_text = huge_stdout * 100  # 50,000+ characters
    record = {
        "event_id": "huge-output-event",
        "command": "cat huge_file.txt",
        "activity_status": "succeeded",
        "ok": True,
        "stdout": huge_text,
        "stderr": "",
        "stdout_truncated": False,
    }

    panel.refresh([], [record])
    panel.command_table.selectRow(0)
    qapp.processEvents()

    stdout_content = panel.inspector_views["stdout"].toPlainText()
    assert len(stdout_content) == len(huge_text)
    assert "[TRUNCATED]" not in stdout_content
    assert "[ACTIVITY LOG TRUNCATED]" not in stdout_content

    # Metadata tab confirms truncated is False
    metadata_content = panel.inspector_views["metadata"].toPlainText()
    assert '"truncated": false' in metadata_content


def test_qt_activity_collapse_controls_expose_an_explicit_expand_action(qapp, tmp_path):
    """Collapsed inspectors advertise a real, visible expand affordance."""
    from PySide6 import QtCore, QtTest, QtWidgets
    from app.cli.desktop_qt.activity import QtActivityPanel

    panel = QtActivityPanel(QtCore, QtWidgets, workspace_root=lambda: tmp_path)
    panel.widget.resize(1000, 700)
    panel.widget.show()
    qapp.processEvents()

    QtTest.QTest.mouseClick(panel.input_toggle, QtCore.Qt.LeftButton)
    qapp.processEvents()

    assert panel.input_panel.isVisible() is False
    assert panel.input_toggle.text() == "▸ Expand Input"
    assert panel.input_toggle.accessibleName() == "Expand Input"
    assert panel.input_toggle.toolTip() == "Expand Input"

    QtTest.QTest.mouseClick(panel.input_toggle, QtCore.Qt.LeftButton)
    qapp.processEvents()

    assert panel.input_panel.isVisible() is True
    assert panel.input_toggle.text() == "▾ Collapse Input"


def test_qt_activity_session_filter_active_badge_and_copy_actions(qapp, tmp_path, monkeypatch):
    """Session rail exposes instant text filtering, active badge, and 1-click clipboard actions."""
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.activity import QtActivityPanel
    from app.cli.desktop_views.activity import WorkspaceSession

    panel = QtActivityPanel(QtCore, QtWidgets, workspace_root=lambda: tmp_path)
    panel.widget.resize(1000, 700)
    panel.widget.show()

    sessions = [
        WorkspaceSession("cw-alpha-project", tmp_path / "cw-alpha-project", 10.0),
        WorkspaceSession("cw-beta-experiment", tmp_path / "cw-beta-experiment", 8.0),
    ]
    panel.refresh(sessions, [])
    panel.reveal_session("cw-alpha-project")
    panel.reveal_session("cw-beta-experiment")
    panel.render()
    qapp.processEvents()

    assert panel.session_model.rowCount() == 2

    # 1. Instant session filter
    panel.session_filter_input.setText("alpha")
    qapp.processEvents()
    assert panel.session_model.rowCount() == 1
    assert panel.state.filtered_sessions()[0].chat_id == "cw-alpha-project"
    assert panel.workplace_filter_input.text() == "alpha"

    panel.session_filter_input.clear()
    qapp.processEvents()
    assert panel.session_model.rowCount() == 2

    # 2. Active badge display
    monkeypatch.setattr("app.chat_identity.get_active_workspace", lambda: "cw-alpha-project")
    panel.render()
    qapp.processEvents()
    assert "cw-alpha-project" in panel.session_active_badge.text()

    # 3. Copy Session ID
    panel.sessions_table.selectRow(0)
    qapp.processEvents()
    panel._copy_selected_session_id()
    assert QtWidgets.QApplication.clipboard().text() == "cw-alpha-project"
    assert "cw-alpha-project" in panel.session_notice.text()

    # 4. Copy Resume Prompt
    panel._copy_selected_resume_prompt()
    expected_prompt = "Tiếp tục làm việc trong workspace cw-alpha-project"
    assert QtWidgets.QApplication.clipboard().text() == expected_prompt


def test_qt_activity_refurbished_features(qapp, tmp_path, monkeypatch):
    """Refurbished UI elements: command stats bar, inspector telemetry, copy CLI and exit code styling."""
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.activity import QtActivityPanel
    from app.cli.desktop_views.activity import WorkspaceSession

    panel = QtActivityPanel(QtCore, QtWidgets, workspace_root=lambda: tmp_path)
    panel.widget.resize(1000, 700)
    panel.widget.show()

    # Verify widget existence and object names
    assert hasattr(panel, "command_stats_bar")
    assert panel.command_stats_bar.objectName() == "activityCommandStatsBar"
    assert hasattr(panel, "inspector_telemetry_label")
    assert panel.inspector_telemetry_label.objectName() == "activityInspectorTelemetry"
    assert hasattr(panel, "_copy_cli_bind_button")

    session = WorkspaceSession("sess-test", tmp_path / "sess-test", 1.0)
    records = [
        {
            "event_id": "ev-1",
            "operation_id": "op-1",
            "chat_id": "sess-test",
            "command": "echo hello",
            "status": "succeeded",
            "ok": True,
            "exit_code": 0,
            "duration_ms": 25,
            "stdout": "hello world\nline 2",
        },
        {
            "event_id": "ev-2",
            "operation_id": "op-2",
            "chat_id": "sess-test",
            "command": "cat non_existent",
            "status": "failed",
            "ok": False,
            "exit_code": 1,
            "duration_ms": 10,
            "stderr": "file not found",
        },
    ]

    panel.refresh([session], records)
    panel.reveal_session("sess-test")
    panel.render()
    qapp.processEvents()

    # 1. Command Stats Bar
    stats_text = panel.command_stats_bar.text()
    assert "2 commands" in stats_text or "2 lệnh" in stats_text
    assert "1 OK" in stats_text
    assert "1 ERR" in stats_text

    # 2. Inspector Telemetry
    panel.command_table.selectRow(0)
    qapp.processEvents()
    panel.inspector.setCurrentIndex(1)  # Tab stdout
    qapp.processEvents()
    telemetry_text = panel.inspector_telemetry_label.text()
    assert "Lines: 2" in telemetry_text or "Dòng: 2" in telemetry_text
    assert "Size:" in telemetry_text or "Cỡ:" in telemetry_text

    # 3. Exit Code styling
    # Row 0 has exit code 0 -> success color
    assert "#42d5ad" in panel.detail_exit_val.styleSheet()
    assert panel.detail_exit_val.text() == "0"

    # Row 1 has exit code 1 -> error color
    panel.command_table.selectRow(1)
    qapp.processEvents()
    assert "#ff6b61" in panel.detail_exit_val.styleSheet()
    assert panel.detail_exit_val.text() == "1"

    # 4. Copy CLI Bind
    panel.sessions_table.selectRow(0)
    qapp.processEvents()
    panel._copy_selected_cli_bind()
    assert QtWidgets.QApplication.clipboard().text() == "bqa session bind sess-test"
    assert "bqa session bind sess-test" in panel.session_notice.text()


