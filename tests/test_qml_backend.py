import os
from pathlib import Path
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtGui import QGuiApplication

from app.cli.center.persistence import CenterWindowStateStore
from app.cli.context import CLIContext
from app.cli.desktop_views.activity import WorkspaceSession
from app.cli.ui_preferences import UIPreferencesStore
import app.qml_ui.backend as qml_backend
from app.qml_ui.backend import CenterQmlBackend


def _app():
    return QGuiApplication.instance() or QGuiApplication(["bqa-qml-test"])


def _ctx(tmp_path: Path) -> CLIContext:
    return CLIContext(
        repo_root=tmp_path,
        values={"HOST_CHAT_ROOT": str(tmp_path / "chats"), "MCP_PORT": "18427"},
        base_url="http://127.0.0.1:18427",
        token="",
        request_timeout=1.0,
    )


def _backend(tmp_path: Path) -> CenterQmlBackend:
    _app()
    return CenterQmlBackend(
        _ctx(tmp_path),
        fixture=True,
        safe_actions=True,
        preferences_store=UIPreferencesStore(tmp_path / "ui.json"),
        window_state_store=CenterWindowStateStore(tmp_path / "window.json"),
    )


def test_qml_backend_fixture_exposes_all_center_views(tmp_path):
    backend = _backend(tmp_path)
    try:
        assert backend.sessionsModel.rowCount() == 6
        assert backend.operationsModel.rowCount() == 24
        assert backend.logsModel.rowCount() == 80
        assert backend.uiFontFamily
        assert backend.monoFontFamily
    finally:
        backend.shutdown()


def test_qml_language_hot_applies_and_stays_out_of_server_env(tmp_path):
    backend = _backend(tmp_path)
    try:
        backend.changeLanguage("vi")
        assert backend.language == "vi"
        assert '"language": "vi"' in (tmp_path / "ui.json").read_text(encoding="utf-8")
        assert not (tmp_path / ".env").exists()
    finally:
        backend.shutdown()


def test_qml_session_selection_filters_commands_without_reordering_sessions(tmp_path):
    backend = _backend(tmp_path)
    try:
        before = [row["chatId"] for row in backend.sessionsModel.rows()]
        target = before[2]
        backend.selectSession(target)
        after = [row["chatId"] for row in backend.sessionsModel.rows()]

        assert after == before
        assert 0 < backend.operationsModel.rowCount() < 24
        assert all(row["chatId"] == target for row in backend.operationsModel.rows())
    finally:
        backend.shutdown()


def test_qml_safe_runtime_action_never_calls_real_lifecycle(tmp_path):
    app = _app()
    backend = _backend(tmp_path)
    try:
        tunnel_before = backend.tunnelPid
        backend.restartBridge()
        deadline = time.monotonic() + 2
        while backend.actionBusy and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)

        assert backend.actionBusy is False
        assert backend.tunnelPid == tunnel_before
        assert backend.toastText.startswith("SAFE VERIFY:")
    finally:
        backend.shutdown()


def test_qml_structured_operation_query_filters_locally(tmp_path):
    backend = _backend(tmp_path)
    try:
        backend.setOperationSearch("status:failed cwd:/safe/workspace")
        rows = backend.operationsModel.rows()

        assert rows
        assert all(row["status"] == "failed" for row in rows)
        assert all(row["cwd"] == "/safe/workspace" for row in rows)

        backend.setOperationSearch('cmd:"pytest -q"')
        rows = backend.operationsModel.rows()
        assert rows
        assert all("pytest -q" in row["command"] for row in rows)
    finally:
        backend.shutdown()


def test_qml_structured_log_query_combines_role_filters(tmp_path):
    backend = _backend(tmp_path)
    try:
        backend.setLogSearch("category:file outcome:success")
        rows = backend.logsModel.rows()

        assert rows
        assert all(row["category"] == "file" for row in rows)
        assert all(row["outcome"] == "success" for row in rows)

        backend.setLogSearch("severity:error")
        rows = backend.logsModel.rows()
        assert rows
        assert all(row["severity"] == "ERROR" for row in rows)
    finally:
        backend.shutdown()


def test_qml_activity_and_logs_cross_navigation_preserves_domain_ids(tmp_path):
    backend = _backend(tmp_path)
    try:
        operation_id = backend.operationsModel.get(0)["operationId"]
        backend.selectOperation(operation_id)
        backend.showRelatedLogsForSelectedOperation()

        assert backend.activePage == "logs"
        related_logs = backend.logsModel.rows()
        assert related_logs
        assert all(row["operationId"] == operation_id for row in related_logs)

        log_id = related_logs[0]["eventId"]
        backend.selectLog(log_id)
        backend.openOperationForSelectedLog()

        assert backend.activePage == "activity"
        assert backend.selectedOperationId == operation_id
        assert backend.selectedSessionId
        assert all(
            row["chatId"] == backend.selectedSessionId
            for row in backend.operationsModel.rows()
        )
    finally:
        backend.shutdown()


def test_qml_window_size_persists_and_clamps_without_position(tmp_path):
    backend = _backend(tmp_path)
    try:
        backend.saveWindowGeometry(1440, 900)
    finally:
        backend.shutdown()

    restored = _backend(tmp_path)
    try:
        assert restored.initialWindowWidth == 1440
        assert restored.initialWindowHeight == 900
        state_text = (tmp_path / "window.json").read_text(encoding="utf-8")
        assert "1440x900" in state_text
        assert '"x"' not in state_text
        assert '"y"' not in state_text

        restored.saveWindowGeometry(300, 200)
    finally:
        restored.shutdown()

    clamped = _backend(tmp_path)
    try:
        assert clamped.initialWindowWidth == 960
        assert clamped.initialWindowHeight == 650
    finally:
        clamped.shutdown()


def test_qml_close_session_persists_empty_selection(tmp_path):
    backend = _backend(tmp_path)
    try:
        target = backend.sessionsModel.get(0)["chatId"]
        backend.selectSession(target)
        backend.closeSelectedSession()

        assert backend.selectedSessionId == ""
        assert target not in {
            row["chatId"] for row in backend.sessionsModel.rows()
        }
        saved = CenterWindowStateStore(tmp_path / "window.json").load()
        assert saved["selected_session"] is None
    finally:
        backend.shutdown()


def test_qml_log_to_operation_reopens_locally_closed_session(tmp_path):
    backend = _backend(tmp_path)
    try:
        operation = backend.operationsModel.get(0)
        operation_id = operation["operationId"]
        chat_id = operation["chatId"]

        backend.selectSession(chat_id)
        backend.closeSelectedSession()
        assert chat_id not in {
            row["chatId"] for row in backend.sessionsModel.rows()
        }

        backend.selectOperation(operation_id)
        backend.showRelatedLogsForSelectedOperation()
        related_logs = backend.logsModel.rows()
        assert related_logs

        backend.selectLog(related_logs[0]["eventId"])
        backend.openOperationForSelectedLog()

        assert backend.activePage == "activity"
        assert backend.selectedSessionId == chat_id
        assert chat_id in {
            row["chatId"] for row in backend.sessionsModel.rows()
        }
        assert backend.selectedOperationId == operation_id
    finally:
        backend.shutdown()


def test_qml_toast_can_be_cleared_after_transient_feedback(tmp_path):
    backend = _backend(tmp_path)
    try:
        backend.copyText("hello")
        assert backend.toastText == "Copied"
        backend.clearToast()
        assert backend.toastText == ""
    finally:
        backend.shutdown()


def test_qml_activity_sort_restores_click_sort_parity(tmp_path):
    backend = _backend(tmp_path)
    try:
        backend.toggleOperationSort("duration")
        ascending = [float(row["duration"]) for row in backend.operationsModel.rows()]
        assert ascending == sorted(ascending)
        assert backend.operationSortKey == "duration"
        assert backend.operationSortDescending is False

        backend.toggleOperationSort("duration")
        descending = [float(row["duration"]) for row in backend.operationsModel.rows()]
        assert descending == sorted(descending, reverse=True)
        assert backend.operationSortDescending is True
    finally:
        backend.shutdown()


def test_qml_log_outcome_filter_is_visible_state_and_clearable(tmp_path):
    backend = _backend(tmp_path)
    try:
        backend.setLogOutcome("failure")
        assert backend.logOutcomeFilter == "failure"
        rows = backend.logsModel.rows()
        assert rows
        assert all(row["outcome"] == "failure" for row in rows)

        backend.setLogCategory("file")
        assert backend.logCategoryFilter == "file"

        backend.clearLogFilters()
        assert backend.logOutcomeFilter == "all"
        assert backend.logCategoryFilter == "all"
    finally:
        backend.shutdown()


def test_qml_refresh_bounds_seen_ids_and_prunes_removed_session_state(tmp_path):
    backend = _backend(tmp_path)
    try:
        backend._seen_operation_ids = {
            f"old-op-{index}" for index in range(2000)
        }
        backend._unread_by_session = {"gone": 9, "keep": 2}
        backend._selected_session = "keep"
        session = WorkspaceSession(
            chat_id="keep",
            path=tmp_path / "keep",
            last_changed=2.0,
            created_at=1.0,
        )
        record = {
            "operation_id": "op-new",
            "event_id": "event-new",
            "timestamp": "2026-08-30T05:00:00+00:00",
            "status": "succeeded",
            "activity_status": "succeeded",
            "command": "echo ok",
            "chat_id": "keep",
            "cwd": str(tmp_path),
            "exit_code": 0,
            "duration_ms": 4,
        }

        backend._apply_refresh(
            {
                "status": {"bridge": "ready"},
                "sessions": [session],
                "records": [record],
            }
        )

        assert backend._seen_operation_ids == {"op-new"}
        assert backend._unread_by_session == {"keep": 2}
    finally:
        backend.shutdown()


def test_qml_expanded_fixture_models_have_operational_data(tmp_path):
    backend = _backend(tmp_path)
    try:
        assert backend.workspacesModel.rowCount() == 8
        assert backend.attentionModel.rowCount() >= 1
        assert backend.healthMetricsModel.rowCount() >= 1
        assert backend.doctorChecksModel.rowCount() >= 1
        assert backend.securityModel.rowCount() >= 1
        assert backend.configChecksModel.rowCount() >= 1
        assert backend.runtimeLogsModel.rowCount() >= 1
        assert backend.activePage == "overview"
    finally:
        backend.shutdown()


def test_qml_workspace_filter_selection_and_cross_navigation(tmp_path):
    backend = _backend(tmp_path)
    try:
        backend.setWorkspaceStateFilter("archived")
        assert backend.workspacesModel.rowCount() == 2
        assert all(row["archived"] for row in backend.workspacesModel.rows())

        backend.setWorkspaceStateFilter("active")
        active = backend.workspacesModel.get(0)
        backend.selectWorkspace(active["chatId"])
        assert backend.selectedWorkspaceId == active["chatId"]
        assert backend.selectedWorkspacePath == active["path"]

        backend.openSelectedWorkspaceActivity()
        assert backend.activePage == "activity"
        assert backend.selectedSessionId == active["chatId"]

        backend.setActivePage("workspaces")
        backend.selectWorkspace(active["chatId"])
        backend.openSelectedWorkspaceLogs()
        assert backend.activePage == "logs"
        assert backend.logsMode == "events"
        assert all(
            active["chatId"].lower() in row["chatId"].lower()
            for row in backend.logsModel.rows()
        )
    finally:
        backend.shutdown()


def test_qml_runtime_log_mode_source_and_search_are_local_in_fixture(tmp_path):
    backend = _backend(tmp_path)
    try:
        backend.setLogsMode("runtime")
        assert backend.logsMode == "runtime"
        assert backend.runtimeLogsModel.rowCount() > 0

        backend.setRuntimeLogSource("tunnel")
        assert backend.runtimeLogSource == "tunnel"
        assert backend.runtimeLogsModel.rowCount() == 12
        assert all(
            row["source"] == "tunnel"
            for row in backend.runtimeLogsModel.rows()
        )

        backend.setRuntimeLogSearch("warning")
        assert backend.runtimeLogsModel.rowCount() > 0
        assert all(
            "warning" in row["line"].lower()
            for row in backend.runtimeLogsModel.rows()
        )
    finally:
        backend.shutdown()


def test_qml_fixture_diagnostics_populates_doctor_without_live_io(tmp_path):
    backend = _backend(tmp_path)
    try:
        backend.runDiagnostics(False)
        assert backend.doctorBusy is False
        assert backend.doctorStatus == "degraded"
        assert backend.doctorWarningCount == 2
        assert backend.doctorFailureCount == 0
        assert backend.doctorChecksModel.rowCount() >= 1
    finally:
        backend.shutdown()


def test_qml_presentation_preferences_hot_apply_and_persist(tmp_path):
    backend = _backend(tmp_path)
    try:
        backend.changeTheme("light")
        backend.changeDensity("comfortable")
        backend.changeFontScale(1.25)

        assert backend.themeName == "light"
        assert backend.density == "comfortable"
        assert backend.fontScale == 1.25
    finally:
        backend.shutdown()

    restored = _backend(tmp_path)
    try:
        assert restored.themeName == "light"
        assert restored.density == "comfortable"
        assert restored.fontScale == 1.25
        assert not (tmp_path / ".env").exists()
    finally:
        restored.shutdown()


def test_qml_safe_workspace_mutations_never_apply_destructive_changes(tmp_path):
    app = _app()
    backend = _backend(tmp_path)
    try:
        archived = next(
            row for row in backend.workspacesModel.rows()
            if row["archived"]
        )
        backend.selectWorkspace(archived["chatId"])
        backend.deleteSelectedWorkspace()
        deadline = time.monotonic() + 2
        while backend.actionBusy and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)

        assert backend.actionBusy is False
        assert backend.toastText.startswith("SAFE VERIFY:")
        assert backend.workspacesModel.find(archived["chatId"]) >= 0
    finally:
        backend.shutdown()


def test_qml_runtime_logs_discard_stale_async_results(tmp_path):
    backend = _backend(tmp_path)
    try:
        backend._runtime_log_generation = 2
        original = backend.runtimeLogsModel.rows()

        backend._apply_runtime_logs(
            {
                "generation": 1,
                "rows": [
                    {
                        "rowId": "stale",
                        "source": "server",
                        "timestamp": "old",
                        "line": "stale result",
                    }
                ],
                "error": "",
            }
        )
        assert backend.runtimeLogsModel.rows() == original

        backend._apply_runtime_logs(
            {
                "generation": 2,
                "rows": [
                    {
                        "rowId": "fresh",
                        "source": "tunnel",
                        "timestamp": "new",
                        "line": "fresh result",
                    }
                ],
                "error": "",
            }
        )
        assert backend.runtimeLogsModel.rows() == [
            {
                "rowId": "fresh",
                "source": "tunnel",
                "timestamp": "new",
                "line": "fresh result",
            }
        ]
    finally:
        backend.shutdown()


def test_qml_runtime_logs_ignore_stale_errors(tmp_path):
    backend = _backend(tmp_path)
    try:
        backend._runtime_log_generation = 4
        backend.clearToast()

        backend._apply_runtime_logs(
            {
                "generation": 3,
                "rows": [],
                "error": "old failure",
            }
        )
        assert backend.toastText == ""

        backend._apply_runtime_logs(
            {
                "generation": 4,
                "rows": [],
                "error": "current failure",
            }
        )
        assert "current failure" in backend.toastText
    finally:
        backend.shutdown()


def test_qml_explicit_full_refresh_is_queued_when_fast_refresh_is_busy(tmp_path):
    backend = _backend(tmp_path)
    try:
        backend.fixture = False
        backend._refresh_busy = True
        backend._action_busy = False
        backend._pending_full_refresh = False

        backend.refreshNow()

        assert backend._pending_full_refresh is True
        assert backend._refresh_busy is True
    finally:
        backend.fixture = True
        backend._refresh_busy = False
        backend.shutdown()


def test_qml_new_command_in_other_session_never_steals_selection_or_reorders(tmp_path):
    backend = _backend(tmp_path)
    try:
        before_rows = backend.sessionsModel.rows()
        before_order = [row["chatId"] for row in before_rows]
        selected = before_order[0]
        other = before_order[1]
        backend.selectSession(selected)

        sessions = [
            WorkspaceSession(
                chat_id=row["chatId"],
                path=tmp_path / row["chatId"],
                last_changed=float(row["lastChanged"]),
                created_at=float(row["createdAt"]),
            )
            for row in backend._sessions_all
        ]
        backend._seen_operation_ids = {"baseline-op"}
        records = [
            {
                "operation_id": "baseline-op",
                "event_id": "baseline-event",
                "timestamp": "2026-08-30T05:00:00+00:00",
                "status": "succeeded",
                "activity_status": "succeeded",
                "command": "echo baseline",
                "chat_id": selected,
                "cwd": str(tmp_path),
                "exit_code": 0,
                "duration_ms": 3,
            },
            {
                "operation_id": "new-other-op",
                "event_id": "new-other-event",
                "timestamp": "2026-08-30T05:00:01+00:00",
                "status": "running",
                "activity_status": "running",
                "command": "echo new",
                "chat_id": other,
                "cwd": str(tmp_path),
                "exit_code": None,
                "duration_ms": 0,
            },
        ]

        backend._apply_refresh(
            {
                "status": backend._status,
                "sessions": sessions,
                "records": records,
            }
        )

        assert backend.selectedSessionId == selected
        assert [row["chatId"] for row in backend.sessionsModel.rows()] == before_order
        assert backend._unread_by_session.get(other) == (
            next(row["unread"] for row in before_rows if row["chatId"] == other) + 1
        )
        assert all(
            row["chatId"] == selected
            for row in backend.operationsModel.rows()
        )
    finally:
        backend.shutdown()


def test_qml_backend_exposes_no_tunnel_stop_slot(tmp_path):
    backend = _backend(tmp_path)
    try:
        method_names = {
            bytes(backend.metaObject().method(index).name()).decode("utf-8")
            for index in range(
                backend.metaObject().methodOffset(),
                backend.metaObject().methodCount(),
            )
        }
        assert "stopService" not in method_names
    finally:
        backend.shutdown()


def test_qml_activity_reader_respects_supported_journal_limit(monkeypatch):
    called = {}

    def fake_read(limit):
        called["limit"] = limit
        return []

    monkeypatch.setattr(qml_backend, "read_mcp_command_activity", fake_read)

    assert qml_backend._project_qml_command_activity() == []
    assert called["limit"] == qml_backend.QML_ACTIVITY_READ_LIMIT == 100


def test_qml_workspace_log_worker_stops_promptly_with_closeable_reader():
    import threading

    class Reader:
        def __init__(self):
            self.closed = threading.Event()

        def __call__(self, _cursor):
            yield {"id": "", "event": "stream_open", "data": {}}
            self.closed.wait(2.0)

        def close(self):
            self.closed.set()

    reader = Reader()
    worker = qml_backend._WorkspaceLogThread(reader)
    worker.start()
    time.sleep(0.05)

    started = time.monotonic()
    worker.stop()

    assert worker.wait(500) is True
    assert time.monotonic() - started < 0.5
