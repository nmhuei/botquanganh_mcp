import os

import pytest


def workspace_log_fixture():
    """A complete event routed through the panel's real queue lifecycle."""
    return {
        "id": "audit-fixture-1",
        "event": "workspace_log",
        "data": {
            "chat_id": "audit-chat",
            "event_action": "host_read_file",
            "category": "filesystem",
            "outcome": "success",
            "duration_ms": 12.5,
            "payload": {"path": "README.md", "offset": 0},
        },
    }


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def test_qt_workspace_log_state_alerts_once_per_live_activity():
    from app.cli.desktop_qt.workspace_logs import WorkspaceLogState

    notices = []
    state = WorkspaceLogState(on_new_activity=notices.append)
    state.accept_control({"event": "stream_replay", "data": {"phase": "start", "baseline": True}})
    state.accept_event({"id": "old", "event": "workspace_log", "data": {"chat_id": "chat-a", "event_action": "host_run_command"}})
    state.accept_control({"event": "stream_replay", "data": {"phase": "complete"}})
    state.accept_event({"id": "live", "event": "workspace_log", "data": {"chat_id": "chat-a", "event_action": "host_run_command"}})
    state.accept_event({"id": "live", "event": "workspace_log", "data": {"chat_id": "chat-a", "event_action": "host_run_command"}})

    assert [(notice.chat_id, notice.operation_id) for notice in notices] == [("chat-a", "live")]


def test_qt_workspace_log_table_model_exposes_rows(qapp):
    from PySide6 import QtCore
    from app.cli.desktop_qt.workspace_logs import WorkspaceLogState, WorkspaceLogTableModel

    state = WorkspaceLogState(on_new_activity=lambda _notice: None)
    state.accept_event({"id": "evt-1", "event": "workspace_log", "data": {"chat_id": "chat-a", "event_action": "host_read_file"}})
    model = WorkspaceLogTableModel(QtCore, state)

    assert model.rowCount() == 1
    assert model.data(model.index(0, 3), QtCore.Qt.DisplayRole) == "host_read_file"


def test_qt_workspace_logs_panel_exposes_dense_audit_layout_contract(qapp):
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.workspace_logs import QtWorkspaceLogsPanel

    panel = QtWorkspaceLogsPanel(QtCore, QtWidgets)
    panel.widget.resize(1_000, 700)
    panel.widget.show()
    qapp.processEvents()

    assert panel.heading.objectName() == "workspaceLogsHeading"
    assert panel.page_heading.title_label is panel.heading
    assert panel.toolbar_frame.objectName() == "denseToolbar"
    assert panel.event_count_label is panel.notice_label
    assert panel.table_frame.objectName() == "workspaceLogsTableFrame"
    assert panel.inspector_frame.objectName() == "workspaceLogsInspectorFrame"
    assert panel.inspector_frame.property("role") == "inspectorSurface"
    assert panel.content_splitter.orientation() == QtCore.Qt.Horizontal
    assert {button.property("role") for button in panel.chip_buttons.values()} == {
        "compactAction"
    }
    assert panel.chip_buttons["all"].property("variant") == "primary"
    assert panel.chip_buttons["error"].property("variant") == "secondary"
    table_size, inspector_size = panel.content_splitter.sizes()
    assert table_size / (table_size + inspector_size) == pytest.approx(0.65, abs=0.05)

    panel.close()


def test_qt_workspace_logs_panel_renders_selected_fixture_in_dense_dark_inspector(qapp):
    """Catch a regression to a light, unframed inspector after selecting an audit event."""
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.theme import build_stylesheet
    from app.cli.desktop_qt.workspace_logs import QtWorkspaceLogsPanel

    root = QtWidgets.QWidget()
    root.setStyleSheet(build_stylesheet())
    layout = QtWidgets.QVBoxLayout(root)
    panel = QtWorkspaceLogsPanel(QtCore, QtWidgets)
    layout.addWidget(panel.widget)
    root.resize(1_000, 700)
    root.show()
    panel.event_queue.put(("event", workspace_log_fixture()))
    panel._drain_queue()
    panel.table.selectRow(0)
    qapp.processEvents()

    assert panel.table.currentIndex().isValid()
    assert panel.state.selected_id == "audit-fixture-1"
    assert "host_read_file" in panel.inspector_views["summary"].toPlainText()
    assert panel.inspector_frame.property("role") == "inspectorSurface"
    assert panel.content_splitter.sizes()[0] > panel.content_splitter.sizes()[1]
    assert panel.event_count_label.text()

    panel.close()
    root.close()


def test_qt_workspace_logs_panel_preserves_selection_through_filter_clear_and_close(qapp):
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.workspace_logs import QtWorkspaceLogsPanel

    panel = QtWorkspaceLogsPanel(QtCore, QtWidgets)
    panel.event_queue.put(
        (
            "event",
            {
                "id": "evt-1",
                "event": "workspace_log",
                "data": {
                    "chat_id": "chat-a",
                    "event_action": "host_read_file",
                    "payload": {"path": "README.md"},
                },
            },
        )
    )
    panel._drain_queue()
    panel.table.selectRow(0)
    qapp.processEvents()

    assert panel.state.selected_id == "evt-1"
    assert "host_read_file" in panel.inspector_views["summary"].toPlainText()

    panel.chat_filter_input.setText("does-not-match")
    qapp.processEvents()

    assert panel.model.rowCount() == 0
    assert panel.state.selected_id == "evt-1"
    assert all(not view.toPlainText() for view in panel.inspector_views.values())

    panel.clear_filters()
    qapp.processEvents()

    assert panel.model.rowCount() == 1
    assert panel.table.currentIndex().isValid()
    assert panel.state.selected_id == "evt-1"

    panel.drain_timer.start()
    panel.close()

    assert panel.closed is True
    assert panel.stop_event.is_set()
    assert not panel.drain_timer.isActive()


def test_qt_workspace_logs_panel_relabels_headers_and_filter_on_locale_change(qapp):
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.workspace_logs import QtWorkspaceLogsPanel
    from app.cli.desktop_views.i18n import DesktopTranslator

    panel = QtWorkspaceLogsPanel(QtCore, QtWidgets, DesktopTranslator("en"))
    panel.set_translator(DesktopTranslator("vi"))

    assert panel.model.headerData(0, QtCore.Qt.Horizontal, QtCore.Qt.DisplayRole) == "Thời gian (UTC)"
    assert panel.chat_filter_label.text() == "Lọc chat"
    panel.close()
