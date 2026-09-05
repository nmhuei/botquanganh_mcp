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
    """Command history and both inspectors remain user-resizable work surfaces."""
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.activity import QtActivityPanel

    panel = QtActivityPanel(QtCore, QtWidgets, workspace_root=lambda: tmp_path)
    panel.widget.resize(1000, 700)
    panel.widget.show()
    qapp.processEvents()

    assert panel.activity_workbench_splitter.orientation() == QtCore.Qt.Vertical
    assert panel.investigation_splitter.orientation() == QtCore.Qt.Horizontal
    assert panel.activity_workbench_splitter.indexOf(panel.command_frame) == 0
    assert panel.activity_workbench_splitter.indexOf(panel.inspection_workspace) == 1
    assert panel.investigation_splitter.indexOf(panel.input_panel) == 0
    assert panel.investigation_splitter.indexOf(panel.output_panel) == 1

    panel.activity_workbench_splitter.setSizes((180, 420))
    panel.investigation_splitter.setSizes((220, 380))
    qapp.processEvents()
    outer_sizes = panel.activity_workbench_splitter.sizes()
    inner_sizes = panel.investigation_splitter.sizes()

    assert outer_sizes[1] > outer_sizes[0]
    assert inner_sizes[1] > inner_sizes[0]

    panel.render()
    qapp.processEvents()

    assert (
        panel.activity_workbench_splitter.sizes()[1]
        > panel.activity_workbench_splitter.sizes()[0]
    )
    assert (
        panel.investigation_splitter.sizes()[1]
        > panel.investigation_splitter.sizes()[0]
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

    assert [
        model.data(model.index(0, column), QtCore.Qt.ToolTipRole)
        for column in range(3)
    ] == ["incident-retrospective", "enabled", "00:00:10"]


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
    panel.investigation_splitter.setSizes((180, 820))
    qapp.processEvents()

    input_view = panel.command_input_view
    output_view = panel.inspector_views["stdout"]
    assert input_view.viewport().width() < 200
    assert input_view.viewport().width() < output_view.viewport().width()
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
    """A click-hidden pane retains a visible, user-reachable restore control."""
    from PySide6 import QtCore, QtTest, QtWidgets
    from app.cli.desktop_qt.activity import QtActivityPanel

    panel = QtActivityPanel(QtCore, QtWidgets, workspace_root=lambda: tmp_path)
    panel.widget.resize(1000, 700)
    panel.widget.show()
    panel.widget.activateWindow()
    qapp.processEvents()
    panel.vertical_splitter.setSizes([240, 360])
    baseline_sizes = panel.vertical_splitter.sizes()

    def click_visible_toggle(button):
        center = button.rect().center()
        assert button.isVisibleTo(panel.widget)
        assert button.isEnabled()
        assert button.accessibleName()
        assert button.visibleRegion().contains(center)
        QtTest.QTest.mouseClick(
            button,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
            center,
        )
        qapp.processEvents()
        assert button.hasFocus()

    click_visible_toggle(panel.input_toggle)
    assert panel.input_collapsed is True
    assert panel.input_panel.isVisible() is False
    assert panel.output_collapsed is False
    assert "Input" in panel.input_toggle.text()

    click_visible_toggle(panel.output_toggle)
    assert panel.output_collapsed is True
    assert panel.output_panel.isVisible() is False

    click_visible_toggle(panel.input_toggle)
    assert panel.input_panel.isVisible() is True
    assert panel.output_panel.isVisible() is False

    click_visible_toggle(panel.output_toggle)
    assert panel.output_panel.isVisible() is True
    assert panel.vertical_splitter.sizes() == baseline_sizes


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
