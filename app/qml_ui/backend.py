"""Backend adapter exposing existing BQA Center services to QML."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shlex
import threading
import time
from typing import Any, Callable

from PySide6.QtCore import (
    QObject,
    Property,
    QAbstractListModel,
    QRunnable,
    QThreadPool,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QFontDatabase, QGuiApplication

from app.activity_log import read_mcp_command_activity
from app.cli.center.invariants import check_tunnel_invariant
from app.cli.config_view import resolve_config_path, set_workspace_config
from app.cli.desktop_views.activity import (
    command_activity_status,
    discover_workspace_sessions,
    project_command_activity_records,
)
from app.cli.desktop_views.workspace_logs import (
    make_workspace_log_stream_reader,
    workspace_log_row_from_mapping,
)
from app.cli.lifecycle import restart, start, status_data
from app.tools.health import health_check
from app.cli.ui_preferences import UIPreferencesStore
from app.cli.center.persistence import CenterWindowStateStore
from app.qml_ui.models import (
    AttentionListModel,
    ConfigCheckListModel,
    DoctorCheckListModel,
    HealthMetricListModel,
    LogListModel,
    OperationListModel,
    RuntimeLogListModel,
    SecurityListModel,
    SessionListModel,
    WorkspaceListModel,
)
from app.cli.center.services import (
    archive_workspace,
    attention_items,
    collect_doctor_snapshot,
    delete_archived_workspace,
    health_metric_rows,
    overall_health,
    restore_workspace,
    runtime_log_rows,
    security_posture,
    system_snapshot,
    workspace_inventory,
    workspace_prune,
    workspace_summary,
)


def _utc_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "—"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return " ".join(text.split())[:26]
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "Z"


def _single_line(value: Any) -> str:
    return " ".join(str(value or "").split())


QML_ACTIVITY_READ_LIMIT = 100


def _project_qml_command_activity() -> list[dict[str, Any]]:
    """Read the bounded command journal using its supported public limit."""
    return project_command_activity_records(
        read_mcp_command_activity(QML_ACTIVITY_READ_LIMIT)
    )


def _json_text(value: Any) -> str:
    try:
        return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return str(value)


def _geometry_size(value: Any) -> tuple[int, int]:
    match = re.match(r"^\s*(\d+)x(\d+)", str(value or ""))
    if not match:
        return 1280, 820
    return max(960, int(match.group(1))), max(650, int(match.group(2)))





def _operation_sort_value(row: dict[str, Any], key: str) -> tuple[int, Any]:
    value = row.get(key)
    if key in {"duration", "exit"}:
        try:
            return (0, float(value))
        except (TypeError, ValueError):
            return (1, str(value or "").lower())
    return (0, str(value or "").lower())


def _matches_query(
    row: dict[str, Any],
    query: str,
    *,
    aliases: dict[str, str],
    free_fields: tuple[str, ...],
) -> bool:
    """Match free text plus lightweight key:value terms entirely in the UI."""
    text = str(query or "").strip()
    if not text:
        return True
    try:
        tokens = shlex.split(text)
    except ValueError:
        tokens = text.split()
    for token in tokens:
        key, separator, wanted = token.partition(":")
        if separator and key.lower() in aliases:
            field = aliases[key.lower()]
            if wanted.lower() not in str(row.get(field) or "").lower():
                return False
            continue
        needle = token.lower()
        if not any(needle in str(row.get(field) or "").lower() for field in free_fields):
            return False
    return True



class _TaskSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class _Task(QRunnable):
    def __init__(self, work: Callable[[], Any]) -> None:
        super().__init__()
        self.work = work
        self.signals = _TaskSignals()

    def run(self) -> None:
        try:
            self.signals.finished.emit(self.work())
        except Exception as exc:
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")


class _WorkspaceLogThread(QObject):
    """Daemon SSE worker that reports into Qt via queued signals.

    A Python daemon thread avoids the fatal QThread-destruction path when a
    synchronous HTTP read is still blocked during application shutdown.
    """

    envelope = Signal(object)
    streamState = Signal(str)

    def __init__(self, reader: Callable[[str | None], Any]) -> None:
        super().__init__()
        self.reader = reader
        self.last_event_id: str | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self.run,
            name="bqa-qml-workspace-logs",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        close_reader = getattr(self.reader, "close", None)
        if callable(close_reader):
            close_reader()

    def wait(self, milliseconds: int) -> bool:
        thread = self._thread
        if thread is None:
            return True
        thread.join(max(0, int(milliseconds)) / 1000.0)
        return not thread.is_alive()

    def isInterruptionRequested(self) -> bool:
        return self._stop_event.is_set()

    def run(self) -> None:
        delay = 0.5
        while not self._stop_event.is_set():
            received = False
            try:
                self.streamState.emit("connecting")
                for envelope in self.reader(self.last_event_id):
                    if self._stop_event.is_set():
                        return
                    event_id = str(envelope.get("id") or "")
                    if event_id:
                        self.last_event_id = event_id
                    event_name = str(envelope.get("event") or "")
                    if event_name == "stream_open":
                        self.streamState.emit("live")
                        received = True
                        continue
                    if event_name in {"workspace_log", "stream_reset", "stream_replay"}:
                        if not received:
                            self.streamState.emit("live")
                        self.envelope.emit(envelope)
                        received = True
                if self._stop_event.is_set():
                    return
                self.streamState.emit("retry")
            except Exception:
                if self._stop_event.is_set():
                    return
                self.streamState.emit("retry")
            delay = 0.5 if received else min(30.0, delay * 2.0)
            if self._stop_event.wait(delay):
                return


class CenterQmlBackend(QObject):
    """One QML-facing facade over the existing Center/runtime services."""

    stateChanged = Signal()
    activePageChanged = Signal()
    languageChanged = Signal()
    selectionChanged = Signal()
    detailsChanged = Signal()
    toastChanged = Signal()
    actionBusyChanged = Signal()

    def __init__(
        self,
        ctx: Any,
        *,
        fixture: bool = False,
        safe_actions: bool = False,
        preferences_store: UIPreferencesStore | None = None,
        window_state_store: CenterWindowStateStore | None = None,
    ) -> None:
        super().__init__()
        self.ctx = ctx
        self.fixture = fixture
        self.safe_actions = safe_actions
        self.preferences_store = preferences_store or UIPreferencesStore()
        self.window_state_store = window_state_store or CenterWindowStateStore()
        self.preferences = self.preferences_store.load(
            legacy_language=(getattr(ctx, "values", {}) or {}).get("BQA_UI_LANGUAGE")
        )
        self.window_state = self.window_state_store.load()
        self._initial_width, self._initial_height = _geometry_size(
            self.window_state.get("geometry")
        )
        self._language = str(self.preferences.get("language") or "en")
        self._theme = str(self.preferences.get("theme") or "classic")
        self._density = str(self.preferences.get("density") or "compact")
        self._font_scale = float(self.preferences.get("font_scale") or 1.0)
        self._active_page = str(self.window_state.get("active_tab") or "overview")
        if self._active_page == "runtime":
            self._active_page = "overview"
        elif self._active_page == "gpt_activity":
            self._active_page = "activity"
        elif self._active_page == "workspace_logs":
            self._active_page = "logs"
        if self._active_page not in {
            "overview", "activity", "workspaces", "logs", "diagnostics", "settings"
        }:
            self._active_page = "overview"

        self.sessions_model = SessionListModel()
        self.operations_model = OperationListModel()
        self.recent_operations_model = OperationListModel()
        self.logs_model = LogListModel()
        self.workspaces_model = WorkspaceListModel()
        self.attention_model = AttentionListModel()
        self.health_metrics_model = HealthMetricListModel()
        self.doctor_checks_model = DoctorCheckListModel()
        self.security_model = SecurityListModel()
        self.config_checks_model = ConfigCheckListModel()
        self.runtime_logs_model = RuntimeLogListModel()

        self._status: dict[str, Any] = {}
        self._health: dict[str, Any] = {}
        self._capabilities: dict[str, Any] = {}
        self._overall: dict[str, str] = {
            "state": "offline",
            "tone": "warning",
            "title": "Loading runtime state",
            "detail": "Waiting for the first system snapshot.",
        }
        self._workspace_summary: dict[str, Any] = {
            "active": 0, "archived": 0, "total": 0, "bytes": 0,
            "bytesText": "0 B", "failures": 0,
        }
        self._doctor: dict[str, Any] = {
            "status": "idle", "warning_count": 0, "failure_count": 0,
        }
        self._doctor_busy = False
        self._runtime_log_source = str(self.window_state.get("runtime_log_source") or "all")
        self._runtime_log_query = ""
        self._runtime_log_generation = 0
        self._logs_mode = str(self.window_state.get("logs_mode") or "events")
        self._selected_workspace = str(self.window_state.get("selected_workspace") or "")

        self._sessions_all: list[dict[str, Any]] = []
        self._operations_all: list[dict[str, Any]] = []
        self._logs_all: list[dict[str, Any]] = []
        self._workspaces_all: list[dict[str, Any]] = []
        self._session_query = ""
        self._operation_query = ""
        self._operation_sort_key = ""
        self._operation_sort_descending = False
        self._workspace_query = ""
        self._workspace_state_filter = "all"
        self._log_query = ""
        self._log_category = "all"
        self._log_outcome = "all"
        self._log_chat = ""
        self._log_operation = ""
        self._selected_session = str(self.window_state.get("selected_session") or "")
        self._selected_operation = ""
        self._selected_log = ""
        self._closed_sessions: set[str] = set()
        self._disabled_sessions: set[str] = set()
        self._seen_operation_ids: set[str] = set()
        self._unread_by_session: dict[str, int] = {}
        self._stream_state = "offline"
        self._toast_text = ""
        self._toast_kind = "info"
        self._action_busy = False
        self._refresh_busy = False
        self._pending_full_refresh = False
        self._last_refresh_time = ""
        self._last_full_refresh_time = ""
        self._last_runtime_log_refresh_time = ""
        self._last_refresh_error = ""
        self._logs_at_live_edge = True
        self._logs_new_count = 0
        self._activity_at_live_edge = True
        self._activity_new_count = 0

        families = set(QFontDatabase.families())
        app_font = QGuiApplication.font().family()
        fixed_font = QFontDatabase.systemFont(QFontDatabase.FixedFont).family()
        self._ui_font = "Noto Sans" if "Noto Sans" in families else app_font
        self._mono_font = "Noto Sans Mono" if "Noto Sans Mono" in families else fixed_font

        self.pool = QThreadPool.globalInstance()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(1400)
        self.refresh_timer.timeout.connect(self.refreshFast)
        self.log_thread: _WorkspaceLogThread | None = None

        if fixture:
            self._seed_fixture()
        else:
            self.refreshNow()
            self.refresh_timer.start()
            self._start_log_stream()

    @Property(QObject, constant=True)
    def sessionsModel(self) -> QObject:
        return self.sessions_model

    @Property(QObject, constant=True)
    def operationsModel(self) -> QObject:
        return self.operations_model

    @Property(QObject, constant=True)
    def recentOperationsModel(self) -> QObject:
        return self.recent_operations_model

    @Property(QObject, constant=True)
    def logsModel(self) -> QObject:
        return self.logs_model

    @Property(QObject, constant=True)
    def workspacesModel(self) -> QObject:
        return self.workspaces_model

    @Property(QObject, constant=True)
    def attentionModel(self) -> QObject:
        return self.attention_model

    @Property(QObject, constant=True)
    def healthMetricsModel(self) -> QObject:
        return self.health_metrics_model

    @Property(QObject, constant=True)
    def doctorChecksModel(self) -> QObject:
        return self.doctor_checks_model

    @Property(QObject, constant=True)
    def securityModel(self) -> QObject:
        return self.security_model

    @Property(QObject, constant=True)
    def configChecksModel(self) -> QObject:
        return self.config_checks_model

    @Property(QObject, constant=True)
    def runtimeLogsModel(self) -> QObject:
        return self.runtime_logs_model

    @Property(str, notify=languageChanged)
    def language(self) -> str:
        return self._language

    @Property(str, notify=stateChanged)
    def themeName(self) -> str:
        return self._theme

    @Property(str, notify=stateChanged)
    def density(self) -> str:
        return self._density

    @Property(float, notify=stateChanged)
    def fontScale(self) -> float:
        return self._font_scale

    @Property(str, notify=activePageChanged)
    def activePage(self) -> str:
        return self._active_page

    @Property(int, constant=True)
    def initialWindowWidth(self) -> int:
        return self._initial_width

    @Property(int, constant=True)
    def initialWindowHeight(self) -> int:
        return self._initial_height

    @Property(str, notify=stateChanged)
    def uiFontFamily(self) -> str:
        return self._ui_font

    @Property(str, notify=stateChanged)
    def monoFontFamily(self) -> str:
        return self._mono_font

    @Property(str, notify=stateChanged)
    def runtimeBadge(self) -> str:
        return str(self._overall.get("state") or "unknown").upper().replace("_", " ")

    @Property(str, notify=stateChanged)
    def runtimeTone(self) -> str:
        return str(self._overall.get("tone") or "warning")

    @Property(str, notify=stateChanged)
    def overallState(self) -> str:
        return str(self._overall.get("state") or "unknown")

    @Property(str, notify=stateChanged)
    def overallTitle(self) -> str:
        return str(self._overall.get("title") or "")

    @Property(str, notify=stateChanged)
    def overallDetail(self) -> str:
        return str(self._overall.get("detail") or "")

    @Property(str, notify=stateChanged)
    def bridgeState(self) -> str:
        return str(self._status.get("bridge") or "unknown")

    @Property(str, notify=stateChanged)
    def serverState(self) -> str:
        return "running" if bool((self._status.get("server") or {}).get("running")) else "stopped"

    @Property(str, notify=stateChanged)
    def tunnelState(self) -> str:
        return "running" if bool((self._status.get("tunnel") or {}).get("running")) else "stopped"

    @Property(str, notify=stateChanged)
    def connectorUrlState(self) -> str:
        return str(self._status.get("url_state") or "unavailable")

    @Property(str, notify=stateChanged)
    def endpoint(self) -> str:
        return str(self._status.get("url") or "—")

    @Property(str, notify=stateChanged)
    def lastKnownEndpoint(self) -> str:
        return str(self._status.get("last_known_url") or "—")

    @Property(str, notify=stateChanged)
    def workspace(self) -> str:
        return str(self._status.get("workspace") or "—")

    @Property(str, notify=stateChanged)
    def serverPid(self) -> str:
        return str((self._status.get("server") or {}).get("pid") or "—")

    @Property(str, notify=stateChanged)
    def tunnelPid(self) -> str:
        return str((self._status.get("tunnel") or {}).get("pid") or "—")

    @Property(bool, notify=stateChanged)
    def authRequired(self) -> bool:
        return bool(self._status.get("auth_required"))

    @Property(str, notify=stateChanged)
    def streamState(self) -> str:
        return self._stream_state.upper()

    @Property(str, notify=stateChanged)
    def sessionSummary(self) -> str:
        return f"{len(self.sessions_model.rows())}/{len(self._sessions_all)} workplaces"

    @Property(int, notify=stateChanged)
    def sessionVisibleCount(self) -> int:
        return len(self.sessions_model.rows())

    @Property(int, notify=stateChanged)
    def sessionTotalCount(self) -> int:
        return len(self._sessions_all)

    @Property(int, notify=stateChanged)
    def visibleOperationCount(self) -> int:
        return len(self.operations_model.rows())

    @Property(str, notify=stateChanged)
    def commandSummary(self) -> str:
        scope = self._selected_session or "all workplaces"
        return f"{scope} · {len(self.operations_model.rows())} commands"

    @Property(int, notify=stateChanged)
    def attentionCount(self) -> int:
        return self.attention_model.rowCount()

    @Property(str, notify=stateChanged)
    def workspaceSummary(self) -> str:
        return (
            f"{self._workspace_summary.get('active', 0)} active · "
            f"{self._workspace_summary.get('archived', 0)} archived · "
            f"{self._workspace_summary.get('bytesText', '0 B')}"
        )

    @Property(int, notify=stateChanged)
    def workspaceActiveCount(self) -> int:
        return int(self._workspace_summary.get("active") or 0)

    @Property(int, notify=stateChanged)
    def workspaceArchivedCount(self) -> int:
        return int(self._workspace_summary.get("archived") or 0)

    @Property(str, notify=stateChanged)
    def workspaceBytesText(self) -> str:
        return str(self._workspace_summary.get("bytesText") or "0 B")

    @Property(str, notify=selectionChanged)
    def selectedWorkspaceId(self) -> str:
        return self._selected_workspace

    @Property(str, notify=detailsChanged)
    def selectedWorkspacePath(self) -> str:
        return str(self.workspaces_model.row_for_key(self._selected_workspace).get("path") or "")

    @Property(str, notify=detailsChanged)
    def selectedWorkspaceState(self) -> str:
        return str(self.workspaces_model.row_for_key(self._selected_workspace).get("workspaceState") or "")

    @Property(str, notify=detailsChanged)
    def selectedWorkspaceSummary(self) -> str:
        row = self.workspaces_model.row_for_key(self._selected_workspace)
        if not row:
            return ""
        return (
            f"{row.get('chatId', '')}\n"
            f"State: {row.get('workspaceState', 'unknown')}\n"
            f"Last active: {row.get('lastActive') or '—'}\n"
            f"Size: {row.get('sizeText') or '0 B'}\n"
            f"Events: {row.get('events', 0)} · Operations: {row.get('operations', 0)} · "
            f"Failures: {row.get('failures', 0)}"
        )

    @Property(str, notify=detailsChanged)
    def selectedWorkspaceLastActive(self) -> str:
        return str(self.workspaces_model.row_for_key(self._selected_workspace).get("lastActive") or "—")

    @Property(str, notify=detailsChanged)
    def selectedWorkspaceSizeText(self) -> str:
        return str(self.workspaces_model.row_for_key(self._selected_workspace).get("sizeText") or "0 B")

    @Property(int, notify=detailsChanged)
    def selectedWorkspaceEvents(self) -> int:
        return int(self.workspaces_model.row_for_key(self._selected_workspace).get("events") or 0)

    @Property(int, notify=detailsChanged)
    def selectedWorkspaceOperations(self) -> int:
        return int(self.workspaces_model.row_for_key(self._selected_workspace).get("operations") or 0)

    @Property(int, notify=detailsChanged)
    def selectedWorkspaceFailures(self) -> int:
        return int(self.workspaces_model.row_for_key(self._selected_workspace).get("failures") or 0)

    @Property(str, notify=stateChanged)
    def workspaceStateFilter(self) -> str:
        return self._workspace_state_filter

    @Property(str, notify=stateChanged)
    def logsMode(self) -> str:
        return self._logs_mode

    @Property(str, notify=stateChanged)
    def runtimeLogSource(self) -> str:
        return self._runtime_log_source

    @Property(str, notify=stateChanged)
    def doctorStatus(self) -> str:
        return str(self._doctor.get("status") or "idle")

    @Property(bool, notify=stateChanged)
    def doctorBusy(self) -> bool:
        return self._doctor_busy

    @Property(int, notify=stateChanged)
    def doctorWarningCount(self) -> int:
        return int(self._doctor.get("warning_count") or 0)

    @Property(int, notify=stateChanged)
    def doctorFailureCount(self) -> int:
        return int(self._doctor.get("failure_count") or 0)

    @Property(str, notify=stateChanged)
    def serviceVersion(self) -> str:
        return str(self._capabilities.get("version") or "—")

    @Property(str, notify=stateChanged)
    def commandPolicy(self) -> str:
        return str((self._capabilities.get("host") or {}).get("command_policy") or "—")

    @Property(str, notify=stateChanged)
    def operationSortKey(self) -> str:
        return self._operation_sort_key

    @Property(bool, notify=stateChanged)
    def operationSortDescending(self) -> bool:
        return self._operation_sort_descending

    @Property(str, notify=stateChanged)
    def logCategoryFilter(self) -> str:
        return self._log_category

    @Property(str, notify=stateChanged)
    def logOutcomeFilter(self) -> str:
        return self._log_outcome

    @Property(str, notify=selectionChanged)
    def selectedSessionId(self) -> str:
        return self._selected_session

    @Property(str, notify=selectionChanged)
    def selectedOperationId(self) -> str:
        return self._selected_operation

    @Property(str, notify=selectionChanged)
    def selectedLogId(self) -> str:
        return self._selected_log

    @Property(str, notify=detailsChanged)
    def operationMetadata(self) -> str:
        return str(self.operations_model.row_for_key(self._selected_operation).get("metadata") or "")

    @Property(str, notify=detailsChanged)
    def operationStdout(self) -> str:
        return str(self.operations_model.row_for_key(self._selected_operation).get("stdout") or "")

    @Property(str, notify=detailsChanged)
    def operationStderr(self) -> str:
        return str(self.operations_model.row_for_key(self._selected_operation).get("stderr") or "")

    @Property(str, notify=detailsChanged)
    def operationHuman(self) -> str:
        return str(self.operations_model.row_for_key(self._selected_operation).get("human") or "")

    @Property(str, notify=detailsChanged)
    def logSummary(self) -> str:
        return str(self.logs_model.row_for_key(self._selected_log).get("summary") or "")

    @Property(str, notify=detailsChanged)
    def logMetadata(self) -> str:
        return str(self.logs_model.row_for_key(self._selected_log).get("metadata") or "")

    @Property(str, notify=detailsChanged)
    def logPayload(self) -> str:
        return str(self.logs_model.row_for_key(self._selected_log).get("payloadText") or "")

    @Property(str, notify=toastChanged)
    def toastText(self) -> str:
        return self._toast_text

    @Property(str, notify=toastChanged)
    def toastKind(self) -> str:
        return self._toast_kind

    @Property(bool, notify=actionBusyChanged)
    def actionBusy(self) -> bool:
        return self._action_busy

    @Property(bool, notify=stateChanged)
    def refreshBusy(self) -> bool:
        return self._refresh_busy

    @Property(str, notify=stateChanged)
    def lastRefreshTime(self) -> str:
        return self._last_refresh_time

    @Property(str, notify=stateChanged)
    def lastFullRefreshTime(self) -> str:
        return self._last_full_refresh_time

    @Property(str, notify=stateChanged)
    def lastRuntimeLogRefreshTime(self) -> str:
        return self._last_runtime_log_refresh_time

    @Property(str, notify=stateChanged)
    def lastRefreshError(self) -> str:
        return self._last_refresh_error

    @Property(int, notify=stateChanged)
    def activityNewCount(self) -> int:
        return self._activity_new_count

    @Property(int, notify=stateChanged)
    def logsNewCount(self) -> int:
        return self._logs_new_count

    @Slot(str)
    def changeLanguage(self, language: str) -> None:
        normalized = "vi" if str(language).lower() == "vi" else "en"
        if normalized == self._language:
            return
        self._language = normalized
        self.preferences["language"] = normalized
        try:
            self.preferences_store.set_language(normalized)
        except Exception as exc:
            self._set_toast("warning", f"UI preference save failed: {exc}")
        self.languageChanged.emit()

    @Slot(str)
    def setActivePage(self, page: str) -> None:
        normalized = "overview" if page == "runtime" else str(page or "")
        if normalized not in {
            "overview", "activity", "workspaces", "logs", "diagnostics", "settings"
        } or normalized == self._active_page:
            return
        self._active_page = normalized
        self.window_state["active_tab"] = normalized
        self._save_window_state()
        if normalized == "logs" and self._logs_mode == "runtime":
            self.refreshRuntimeLogs()
        self.activePageChanged.emit()
        self.stateChanged.emit()

    @Slot(str)
    def changeTheme(self, theme: str) -> None:
        try:
            normalized = self.preferences_store.set_theme(theme)
        except Exception as exc:
            self._set_toast("warning", f"UI preference save failed: {exc}")
            return
        self._theme = normalized
        self.preferences["theme"] = normalized
        self.stateChanged.emit()

    @Slot(str)
    def changeDensity(self, density: str) -> None:
        try:
            normalized = self.preferences_store.set_density(density)
        except Exception as exc:
            self._set_toast("warning", f"UI preference save failed: {exc}")
            return
        self._density = normalized
        self.preferences["density"] = normalized
        self.stateChanged.emit()

    @Slot(float)
    def changeFontScale(self, scale: float) -> None:
        try:
            normalized = self.preferences_store.set_font_scale(scale)
        except Exception as exc:
            self._set_toast("warning", f"UI preference save failed: {exc}")
            return
        self._font_scale = float(normalized)
        self.preferences["font_scale"] = normalized
        self.stateChanged.emit()

    @Slot(int, int)
    def saveWindowGeometry(self, width: int, height: int) -> None:
        self.window_state["geometry"] = (
            f"{max(960, int(width))}x{max(650, int(height))}"
        )
        self._save_window_state()

    @Slot(str)
    def setSessionSearch(self, value: str) -> None:
        self._session_query = value.strip().lower()
        self._rebuild_sessions()

    @Slot(str)
    def setOperationSearch(self, value: str) -> None:
        self._operation_query = value.strip().lower()
        self._rebuild_operations()

    @Slot(str)
    def setWorkspaceSearch(self, value: str) -> None:
        self._workspace_query = str(value or "").strip().lower()
        self._rebuild_workspaces()

    @Slot(str)
    def setWorkspaceStateFilter(self, value: str) -> None:
        normalized = str(value or "all").lower()
        self._workspace_state_filter = normalized if normalized in {"all", "active", "archived"} else "all"
        self._rebuild_workspaces()

    @Slot(int)
    def selectWorkspaceAt(self, row: int) -> None:
        item = self.workspaces_model.get(int(row))
        if item:
            self.selectWorkspace(str(item.get("chatId") or ""))

    @Slot(str)
    def selectWorkspace(self, chat_id: str) -> None:
        self._selected_workspace = str(chat_id or "")
        self.window_state["selected_workspace"] = self._selected_workspace or None
        self._save_window_state()
        self.selectionChanged.emit()
        self.detailsChanged.emit()
        self.stateChanged.emit()

    @Slot()
    def openSelectedWorkspaceActivity(self) -> None:
        if not self._selected_workspace:
            return
        self._closed_sessions.discard(self._selected_workspace)
        self.selectSession(self._selected_workspace)
        self.setActivePage("activity")

    @Slot()
    def openSelectedWorkspaceLogs(self) -> None:
        if not self._selected_workspace:
            return
        self._log_chat = self._selected_workspace.lower()
        self._log_operation = ""
        self._logs_mode = "events"
        self.window_state["logs_mode"] = "events"
        self._rebuild_logs()
        self.setActivePage("logs")

    @Slot(str)
    def setLogsMode(self, mode: str) -> None:
        normalized = str(mode or "events").lower()
        if normalized not in {"events", "runtime"}:
            return
        self._logs_mode = normalized
        self.window_state["logs_mode"] = normalized
        self._save_window_state()
        if normalized == "runtime":
            self.refreshRuntimeLogs()
        self.stateChanged.emit()

    @Slot(str)
    def setRuntimeLogSource(self, source: str) -> None:
        normalized = str(source or "all").lower()
        if normalized not in {"all", "server", "tunnel", "launcher", "audit", "desktop"}:
            return
        self._runtime_log_source = normalized
        self.window_state["runtime_log_source"] = normalized
        self._save_window_state()
        self.refreshRuntimeLogs()

    @Slot(str)
    def setRuntimeLogSearch(self, query: str) -> None:
        self._runtime_log_query = str(query or "").strip()
        self.refreshRuntimeLogs()

    @Slot(int)
    def selectSessionAt(self, row: int) -> None:
        item = self.sessions_model.get(int(row))
        if item:
            self.selectSession(str(item.get("chatId") or ""))

    @Slot(int)
    def selectOperationAt(self, row: int) -> None:
        item = self.operations_model.get(int(row))
        if item:
            self.selectOperation(str(item.get("operationId") or ""))

    @Slot(int)
    def selectLogAt(self, row: int) -> None:
        item = self.logs_model.get(int(row))
        if item:
            self.selectLog(str(item.get("eventId") or ""))

    @Slot(str)
    def selectSession(self, chat_id: str) -> None:
        self._selected_session = str(chat_id or "")
        if self._selected_session:
            self._unread_by_session[self._selected_session] = 0
        self.window_state["selected_session"] = self._selected_session or None
        self._save_window_state()
        self._rebuild_sessions()
        self._rebuild_operations()
        self.selectionChanged.emit()
        self.stateChanged.emit()

    @Slot()
    def showAllSessions(self) -> None:
        self.selectSession("")

    @Slot()
    def enableSelectedSession(self) -> None:
        if self._selected_session:
            self._disabled_sessions.discard(self._selected_session)
            self._rebuild_sessions()

    @Slot()
    def disableSelectedSession(self) -> None:
        if self._selected_session:
            self._disabled_sessions.add(self._selected_session)
            self._rebuild_sessions()

    @Slot()
    def closeSelectedSession(self) -> None:
        if not self._selected_session:
            return
        self._closed_sessions.add(self._selected_session)
        self._selected_session = ""
        self.window_state["selected_session"] = None
        self._save_window_state()
        self._rebuild_sessions()
        self._rebuild_operations()
        self.selectionChanged.emit()
        self.stateChanged.emit()

    @Slot(str)
    def selectOperation(self, operation_id: str) -> None:
        self._selected_operation = str(operation_id or "")
        self.selectionChanged.emit()
        self.detailsChanged.emit()

    @Slot(str)
    def selectLog(self, event_id: str) -> None:
        self._selected_log = str(event_id or "")
        self.selectionChanged.emit()
        self.detailsChanged.emit()

    @Slot()
    def showRelatedLogsForSelectedOperation(self) -> None:
        if not self._selected_operation:
            return
        self._log_operation = self._selected_operation
        self._logs_mode = "events"
        self.window_state["logs_mode"] = "events"
        self._rebuild_logs()
        self.setActivePage("logs")

    @Slot()
    def openOperationForSelectedLog(self) -> None:
        log_row = self.logs_model.row_for_key(self._selected_log)
        operation_id = str(log_row.get("operationId") or "")
        if not operation_id:
            return
        operation = next(
            (
                row
                for row in self._operations_all
                if row.get("operationId") == operation_id
            ),
            None,
        )
        if operation is None:
            self._set_toast("warning", "Related operation is not in the local cache.")
            return
        self._selected_session = str(operation.get("chatId") or "")
        self._closed_sessions.discard(self._selected_session)
        self._selected_operation = operation_id
        self._unread_by_session[self._selected_session] = 0
        self.window_state["selected_session"] = self._selected_session or None
        self._save_window_state()
        self._rebuild_sessions()
        self._rebuild_operations()
        self.selectionChanged.emit()
        self.detailsChanged.emit()
        self.setActivePage("activity")

    @Slot(bool)
    def setActivityAtLiveEdge(self, at_edge: bool) -> None:
        self._activity_at_live_edge = bool(at_edge)
        if at_edge and self._activity_new_count:
            self._activity_new_count = 0
            self.stateChanged.emit()

    @Slot(bool)
    def setLogsAtLiveEdge(self, at_edge: bool) -> None:
        self._logs_at_live_edge = bool(at_edge)
        if at_edge and self._logs_new_count:
            self._logs_new_count = 0
            self.stateChanged.emit()

    @Slot()
    def clearActivityNewCount(self) -> None:
        self._activity_new_count = 0
        self.stateChanged.emit()

    @Slot()
    def clearLogsNewCount(self) -> None:
        self._logs_new_count = 0
        self.stateChanged.emit()

    @Slot(str)
    def toggleOperationSort(self, key: str) -> None:
        normalized = str(key or "").lower()
        if normalized not in {"utc", "status", "command", "exit", "duration"}:
            return
        if normalized == self._operation_sort_key:
            self._operation_sort_descending = not self._operation_sort_descending
        else:
            self._operation_sort_key = normalized
            self._operation_sort_descending = False
        self._rebuild_operations()

    @Slot(str)
    def setLogCategory(self, value: str) -> None:
        self._log_category = str(value or "all").lower()
        self._rebuild_logs()

    @Slot(str)
    def setLogOutcome(self, value: str) -> None:
        self._log_outcome = str(value or "all").lower()
        self._rebuild_logs()

    @Slot(str)
    def setLogChatSearch(self, value: str) -> None:
        self._log_chat = value.strip().lower()
        self._rebuild_logs()

    @Slot(str)
    def setLogSearch(self, value: str) -> None:
        self._log_query = value.strip().lower()
        self._rebuild_logs()

    @Slot()
    def clearLogFilters(self) -> None:
        self._log_category = "all"
        self._log_outcome = "all"
        self._log_chat = ""
        self._log_query = ""
        self._log_operation = ""
        self._rebuild_logs()

    def _chat_root_path(self) -> Path:
        values = dict(getattr(self.ctx, "values", {}) or {})
        raw_root = str(values.get("HOST_CHAT_ROOT") or "~/Downloads/bqa-workspaces")
        return resolve_config_path(Path(self.ctx.repo_root), raw_root)

    @Slot()
    def archiveSelectedWorkspace(self) -> None:
        if not self._selected_workspace:
            return
        chat_id = self._selected_workspace
        root = self._chat_root_path()
        self._run_action(
            "archive workspace",
            lambda: archive_workspace(root, chat_id),
        )

    @Slot()
    def restoreSelectedWorkspace(self) -> None:
        if not self._selected_workspace:
            return
        chat_id = self._selected_workspace
        root = self._chat_root_path()
        self._run_action(
            "restore workspace",
            lambda: restore_workspace(root, chat_id),
        )

    @Slot()
    def deleteSelectedWorkspace(self) -> None:
        if not self._selected_workspace:
            return
        chat_id = self._selected_workspace
        root = self._chat_root_path()
        self._run_action(
            "delete archived workspace",
            lambda: delete_archived_workspace(root, chat_id),
        )

    @Slot(bool)
    def pruneWorkspaces(self, apply: bool) -> None:
        root = self._chat_root_path()
        values = dict(getattr(self.ctx, "values", {}) or {})
        if self.safe_actions and apply:
            actual_apply = False
        else:
            actual_apply = bool(apply)

        def work() -> dict[str, Any]:
            result = workspace_prune(root, values, apply=actual_apply)
            if self.safe_actions and apply:
                result["message"] = (
                    "SAFE VERIFY: prune apply converted to dry-run · "
                    + str(result.get("message") or "")
                )
            return result

        self._run_action("prune workspaces", work)

    @Slot()
    def refreshRuntimeLogs(self) -> None:
        self._runtime_log_generation += 1
        generation = self._runtime_log_generation
        source = self._runtime_log_source
        query = self._runtime_log_query

        if self.fixture:
            self._seed_fixture_runtime_logs()
            return

        def work() -> dict[str, Any]:
            try:
                rows = runtime_log_rows(
                    Path(self.ctx.repo_root),
                    source=source,
                    lines=300,
                    query=query,
                )
                return {
                    "generation": generation,
                    "rows": rows,
                    "error": "",
                }
            except Exception as exc:
                return {
                    "generation": generation,
                    "rows": [],
                    "error": f"{type(exc).__name__}: {exc}",
                }

        task = _Task(work)
        task.signals.finished.connect(self._apply_runtime_logs)
        self.pool.start(task)

    @Slot(object)
    def _apply_runtime_logs(self, payload: object) -> None:
        data = dict(payload or {})
        try:
            generation = int(data.get("generation") or 0)
        except (TypeError, ValueError):
            return
        if generation != self._runtime_log_generation:
            return
        error = str(data.get("error") or "")
        if error:
            self._set_toast("warning", f"Runtime log refresh failed: {error}")
            return
        rows = list(data.get("rows") or [])
        self.runtime_logs_model.sync(rows)
        self._last_runtime_log_refresh_time = datetime.now().astimezone().strftime("%H:%M:%S")
        self.stateChanged.emit()

    @Slot(bool)
    def runDiagnostics(self, local_only: bool = False) -> None:
        if self._doctor_busy:
            return
        if self.fixture:
            self._seed_fixture_doctor()
            return
        self._doctor_busy = True
        self.stateChanged.emit()

        def work() -> dict[str, Any]:
            return collect_doctor_snapshot(self.ctx, local_only=bool(local_only))

        task = _Task(work)
        task.signals.finished.connect(self._apply_doctor)
        task.signals.failed.connect(self._doctor_failed)
        self.pool.start(task)

    @Slot(object)
    def _apply_doctor(self, payload: object) -> None:
        self._doctor_busy = False
        self._doctor = dict(payload or {})
        self.doctor_checks_model.sync(self._doctor.get("checks") or [])
        self.config_checks_model.sync(self._doctor.get("config_checks") or [])
        self.stateChanged.emit()

    @Slot(str)
    def _doctor_failed(self, error: str) -> None:
        self._doctor_busy = False
        self._doctor = {
            "status": "failed",
            "warning_count": 0,
            "failure_count": 1,
        }
        self.stateChanged.emit()
        self._set_toast("error", f"Diagnostics failed: {error}")

    @Slot(str)
    def performAttentionAction(self, item_id: str) -> None:
        item = str(item_id or "")
        if item == "server-offline":
            self.startService()
        elif item in {"bridge-not-ready", "server-errors"} or item.startswith("config-"):
            self.setActivePage("diagnostics")
            self.runDiagnostics(False)
        elif item == "tunnel-offline":
            self._logs_mode = "runtime"
            self._runtime_log_source = "tunnel"
            self.setActivePage("logs")
            self.refreshRuntimeLogs()
        elif item in {"auth-failures", "rate-limits"}:
            self._logs_mode = "runtime"
            self._runtime_log_source = "audit"
            self.setActivePage("logs")
            self.refreshRuntimeLogs()
        elif item == "stream-state":
            self._logs_mode = "runtime"
            self._runtime_log_source = "desktop"
            self.setActivePage("logs")
            self.refreshRuntimeLogs()
        elif item == "public-auth-disabled":
            self.setActivePage("settings")
        else:
            self.refreshNow()

    @Slot()
    def refreshFast(self) -> None:
        """Refresh volatile runtime/activity state without rescanning workspace journals."""
        if self.fixture or self._refresh_busy or self._action_busy:
            return
        self._refresh_busy = True
        self.stateChanged.emit()
        config_checks = self.config_checks_model.rows()
        stream_state = self._stream_state

        def work() -> dict[str, Any]:
            values = dict(getattr(self.ctx, "values", {}) or {})
            runtime = status_data(Path(self.ctx.repo_root), values)
            health = health_check()
            chat_root = self._chat_root_path()
            return {
                "refresh_kind": "fast",
                "status": runtime,
                "health": health,
                "overall": overall_health(
                    runtime,
                    health,
                    stream_state,
                    config_checks,
                ),
                "attention": attention_items(
                    runtime,
                    health,
                    stream_state,
                    config_checks,
                ),
                "health_metrics": health_metric_rows(health),
                "sessions": discover_workspace_sessions(chat_root),
                "records": _project_qml_command_activity(),
            }

        task = _Task(work)
        task.signals.finished.connect(self._apply_refresh)
        task.signals.failed.connect(self._refresh_failed)
        self.pool.start(task)

    @Slot()
    def refreshNow(self) -> None:
        """Run a full operator snapshot, including workspace/config/security data."""
        if self.fixture:
            return
        if self._refresh_busy or self._action_busy:
            self._pending_full_refresh = True
            return
        self._pending_full_refresh = False
        self._refresh_busy = True
        self.stateChanged.emit()

        def work() -> dict[str, Any]:
            snapshot = system_snapshot(self.ctx, stream_state=self._stream_state)
            chat_root = self._chat_root_path()
            return {
                **snapshot,
                "refresh_kind": "full",
                "status": snapshot["runtime"],
                "sessions": discover_workspace_sessions(chat_root),
                "records": _project_qml_command_activity(),
            }

        task = _Task(work)
        task.signals.finished.connect(self._apply_refresh)
        task.signals.failed.connect(self._refresh_failed)
        self.pool.start(task)

    @Slot(object)
    def _apply_refresh(self, payload: object) -> None:
        self._refresh_busy = False
        data = dict(payload or {})
        refreshed_at = datetime.now().astimezone().strftime("%H:%M:%S")
        self._last_refresh_time = refreshed_at
        if str(data.get("refresh_kind") or "") == "full":
            self._last_full_refresh_time = refreshed_at
        self._last_refresh_error = ""
        if "status" in data:
            self._status = dict(data.get("status") or {})
        if "health" in data:
            self._health = dict(data.get("health") or {})
        if "capabilities" in data:
            self._capabilities = dict(data.get("capabilities") or {})
        if "overall" in data:
            self._overall = dict(data.get("overall") or self._overall)
        if "workspace_summary" in data:
            self._workspace_summary = dict(
                data.get("workspace_summary") or self._workspace_summary
            )
        if "workspaces" in data:
            self._workspaces_all = list(data.get("workspaces") or [])
            self._rebuild_workspaces()
        if "attention" in data:
            self.attention_model.sync(data.get("attention") or [])
        if "health_metrics" in data:
            self.health_metrics_model.sync(data.get("health_metrics") or [])
        if "security" in data:
            self.security_model.sync(data.get("security") or [])
        if "config_checks" in data:
            self.config_checks_model.sync(data.get("config_checks") or [])
        sessions = list(data.get("sessions") or [])
        records = list(data.get("records") or [])
        current_operation_ids = {
            str(record.get("operation_id") or record.get("event_id") or "")
            for record in records
            if record.get("operation_id") or record.get("event_id")
        }
        new_ids = current_operation_ids - self._seen_operation_ids
        if self._seen_operation_ids:
            for record in records:
                operation_id = str(record.get("operation_id") or record.get("event_id") or "")
                chat_id = str(record.get("chat_id") or "")
                if operation_id in new_ids and chat_id:
                    if chat_id != self._selected_session:
                        self._unread_by_session[chat_id] = self._unread_by_session.get(chat_id, 0) + 1
                    if not self._activity_at_live_edge:
                        self._activity_new_count += 1
        # The activity reader itself is bounded; mirror only its current
        # identity window instead of retaining every operation ever observed.
        self._seen_operation_ids = current_operation_ids

        running = {
            str(record.get("chat_id") or "")
            for record in records
            if command_activity_status(record) == "running"
        }
        self._sessions_all = [
            {
                "chatId": session.chat_id,
                "displayName": session.chat_id,
                "createdAt": session.created_at,
                "lastChanged": session.last_changed,
                "sessionState": (
                    "RUNNING"
                    if session.chat_id in running
                    else "disabled"
                    if session.chat_id in self._disabled_sessions
                    else "enabled"
                ),
            }
            for session in sessions
        ]
        available = {row["chatId"] for row in self._sessions_all}
        self._closed_sessions.intersection_update(available)
        self._disabled_sessions.intersection_update(available)
        self._unread_by_session = {
            chat_id: count
            for chat_id, count in self._unread_by_session.items()
            if chat_id in available
        }
        if self._selected_session and self._selected_session not in available:
            self._selected_session = ""
            self.selectionChanged.emit()

        workspace_ids = {str(row.get("chatId") or "") for row in self._workspaces_all}
        if self._selected_workspace and self._selected_workspace not in workspace_ids:
            self._selected_workspace = ""
            self.window_state["selected_workspace"] = None
            self._save_window_state()
            self.selectionChanged.emit()
            self.detailsChanged.emit()

        self._operations_all = [self._operation_row(record) for record in records]
        self.recent_operations_model.sync(self._operations_all[:8])
        self._rebuild_sessions()
        self._rebuild_operations()
        self.stateChanged.emit()
        self._drain_pending_full_refresh()

    def _drain_pending_full_refresh(self) -> None:
        if (
            self._pending_full_refresh
            and not self.fixture
            and not self._refresh_busy
            and not self._action_busy
        ):
            QTimer.singleShot(0, self.refreshNow)

    @Slot(str)
    def _refresh_failed(self, error: str) -> None:
        self._refresh_busy = False
        self._last_refresh_error = str(error or "unknown refresh error")
        self.stateChanged.emit()
        self._set_toast("warning", f"Refresh failed: {error}")
        self._drain_pending_full_refresh()

    def _start_log_stream(self) -> None:
        if self.fixture or self.log_thread is not None:
            return
        thread = _WorkspaceLogThread(
            make_workspace_log_stream_reader(self.ctx)
        )
        thread.envelope.connect(self._on_log_envelope)
        thread.streamState.connect(self._set_stream_state)
        self.log_thread = thread
        thread.start()

    @Slot(object)
    def _on_log_envelope(self, envelope: object) -> None:
        mapping = dict(envelope or {})
        event_name = str(mapping.get("event") or "")
        if event_name == "stream_reset":
            self._logs_all.clear()
            self._rebuild_logs()
            return
        if event_name != "workspace_log":
            return
        row = workspace_log_row_from_mapping(
            mapping.get("data") or {},
            event_id=str(mapping.get("id") or ""),
        )
        if row is None:
            return
        if row.event_id and any(item["eventId"] == row.event_id for item in self._logs_all):
            return
        self._logs_all.insert(0, self._log_row(row))
        del self._logs_all[5000:]
        if not self._logs_at_live_edge:
            self._logs_new_count += 1
        self._rebuild_logs()
        self.stateChanged.emit()

    @Slot(str)
    def _set_stream_state(self, state: str) -> None:
        self._stream_state = state
        config_checks = self.config_checks_model.rows()
        self._overall = overall_health(
            self._status,
            self._health,
            self._stream_state,
            config_checks,
        )
        self.attention_model.sync(
            attention_items(
                self._status,
                self._health,
                self._stream_state,
                config_checks,
            )
        )
        self.stateChanged.emit()

    @Slot()
    def startService(self) -> None:
        self._run_action("start", lambda: start(Path(self.ctx.repo_root)))

    @Slot()
    def restartBridge(self) -> None:
        def work() -> dict[str, Any]:
            values = dict(getattr(self.ctx, "values", {}) or {})
            before = status_data(Path(self.ctx.repo_root), values)
            result = restart(Path(self.ctx.repo_root), values)
            after = status_data(Path(self.ctx.repo_root), values)
            invariant = check_tunnel_invariant(before, after)
            if not invariant.ok:
                return {"ok": False, "message": f"SAFETY VIOLATION: {invariant.error}"}
            return dict(result or {})

        self._run_action("restart bridge", work)

    @Slot(str)
    def applyWorkspace(self, path: str) -> None:
        selected = str(path or "").replace("file://", "", 1)

        def work() -> dict[str, Any]:
            if self.safe_actions:
                return {"ok": True, "message": "SAFE VERIFY: workspace applied"}
            updates = set_workspace_config(Path(self.ctx.repo_root), selected)
            self.ctx.values.update(updates)
            values = dict(self.ctx.values)
            before = status_data(Path(self.ctx.repo_root), values)
            result = restart(Path(self.ctx.repo_root), values)
            after = status_data(Path(self.ctx.repo_root), values)
            invariant = check_tunnel_invariant(before, after)
            if not invariant.ok:
                return {"ok": False, "message": f"SAFETY VIOLATION: {invariant.error}"}
            return {
                "ok": bool((result or {}).get("ok", True)),
                "message": "Workspace saved",
            }

        self._run_action("apply workspace", work)

    def _run_action(self, name: str, work: Callable[[], dict[str, Any]]) -> None:
        if self._action_busy:
            return
        self._action_busy = True
        self.actionBusyChanged.emit()
        actual = (
            (lambda: {"ok": True, "message": f"SAFE VERIFY: {name}"})
            if self.safe_actions
            else work
        )
        task = _Task(actual)
        task.signals.finished.connect(self._action_finished)
        task.signals.failed.connect(self._action_failed)
        self.pool.start(task)

    @Slot(object)
    def _action_finished(self, result: object) -> None:
        self._action_busy = False
        self.actionBusyChanged.emit()
        data = dict(result or {})
        self._set_toast(
            "success" if data.get("ok", True) else "error",
            str(data.get("message") or "Action completed"),
        )
        if not self.fixture:
            self.refreshNow()

    @Slot(str)
    def _action_failed(self, error: str) -> None:
        self._action_busy = False
        self.actionBusyChanged.emit()
        self._set_toast("error", error)

    @Slot(str)
    def copyText(self, value: str) -> None:
        QGuiApplication.clipboard().setText(str(value or ""))
        self._set_toast("success", "Copied")

    def _operation_row(self, record: dict[str, Any]) -> dict[str, Any]:
        status = command_activity_status(record)
        operation_id = str(record.get("operation_id") or record.get("event_id") or "")
        exit_value = (
            "timeout"
            if status == "timed_out" or record.get("timed_out")
            else str(record.get("exit_code") if record.get("exit_code") is not None else "—")
        )
        duration = record.get("duration_ms")
        try:
            duration_text = f"{float(duration):.0f}" if duration is not None else "—"
        except (TypeError, ValueError):
            duration_text = str(duration or "—")
        metadata = {key: value for key, value in record.items() if key not in {"stdout", "stderr"}}
        command = _single_line(record.get("command"))
        human = "\n".join(
            part
            for part in (
                f"Status: {status.upper()}",
                f"Command: {command}" if command else "",
                f"CWD: {record.get('cwd')}" if record.get("cwd") else "",
                f"Exit: {exit_value}",
                f"Duration: {duration_text} ms" if duration_text != "—" else "",
            )
            if part
        )
        return {
            "operationId": operation_id,
            "utc": _utc_text(record.get("timestamp")),
            "status": status,
            "command": command,
            "exit": exit_value,
            "duration": duration_text,
            "chatId": str(record.get("chat_id") or ""),
            "cwd": str(record.get("cwd") or ""),
            "stdout": str(record.get("stdout") or ""),
            "stderr": str(record.get("stderr") or ""),
            "metadata": _json_text(metadata),
            "human": human,
        }

    def _log_row(self, row: Any) -> dict[str, Any]:
        metadata = asdict(row)
        payload = metadata.pop("payload", None)
        summary = "\n".join(
            part
            for part in (
                f"{row.severity} · {row.category} · {row.outcome}",
                f"Action: {row.action}" if row.action else "",
                f"Session: {row.chat_id}" if row.chat_id else "",
                f"Operation: {row.interaction_id}" if row.interaction_id else "",
            )
            if part
        )
        return {
            "eventId": row.event_id or f"{row.interaction_id}:{row.timestamp}",
            "utc": _utc_text(row.timestamp),
            "severity": row.severity,
            "category": row.category,
            "action": row.action,
            "outcome": row.outcome,
            "duration": f"{row.duration_ms:.1f}" if row.duration_ms is not None else "—",
            "chatId": row.chat_id,
            "operationId": row.interaction_id,
            "summary": summary,
            "metadata": _json_text(metadata),
            "payloadText": _json_text(payload),
        }

    def _rebuild_workspaces(self) -> None:
        rows: list[dict[str, Any]] = []
        for item in self._workspaces_all:
            state = str(item.get("workspaceState") or "active").lower()
            if self._workspace_state_filter not in {"", "all"} and state != self._workspace_state_filter:
                continue
            query = self._workspace_query
            if query and not any(
                query in str(item.get(field) or "").lower()
                for field in ("chatId", "label", "path", "workspaceState")
            ):
                continue
            rows.append(item)
        self.workspaces_model.sync(rows)
        if self._selected_workspace and self.workspaces_model.find(self._selected_workspace) < 0:
            self._selected_workspace = ""
            self.window_state["selected_workspace"] = None
            self._save_window_state()
            self.selectionChanged.emit()
            self.detailsChanged.emit()
        self.stateChanged.emit()

    def _rebuild_sessions(self) -> None:
        rows: list[dict[str, Any]] = []
        for item in self._sessions_all:
            chat_id = item["chatId"]
            if chat_id in self._closed_sessions:
                continue
            if self._session_query and self._session_query not in chat_id.lower():
                continue
            rows.append(
                {
                    **item,
                    "last": (
                        datetime.fromtimestamp(
                            float(item.get("lastChanged") or 0),
                            tz=timezone.utc,
                        ).strftime("%H:%M:%S")
                        if item.get("lastChanged")
                        else "—"
                    ),
                    "unread": self._unread_by_session.get(chat_id, 0),
                    "running": item.get("sessionState") == "RUNNING",
                    "tracked": chat_id not in self._disabled_sessions,
                    "closed": False,
                }
            )
        self.sessions_model.sync(rows)
        self.stateChanged.emit()

    def _rebuild_operations(self) -> None:
        rows: list[dict[str, Any]] = []
        for item in self._operations_all:
            if self._selected_session and item["chatId"] != self._selected_session:
                continue
            if not _matches_query(
                item,
                self._operation_query,
                aliases={
                    "status": "status",
                    "chat": "chatId",
                    "cwd": "cwd",
                    "exit": "exit",
                    "cmd": "command",
                    "command": "command",
                },
                free_fields=("command", "status", "exit", "chatId", "cwd"),
            ):
                continue
            rows.append(item)
        if self._operation_sort_key:
            rows.sort(
                key=lambda row: _operation_sort_value(
                    row,
                    self._operation_sort_key,
                ),
                reverse=self._operation_sort_descending,
            )
        self.operations_model.sync(rows)
        if self._selected_operation and self.operations_model.find(self._selected_operation) < 0:
            self._selected_operation = ""
            self.selectionChanged.emit()
            self.detailsChanged.emit()
        self.stateChanged.emit()

    def _rebuild_logs(self) -> None:
        rows: list[dict[str, Any]] = []
        for item in self._logs_all:
            category = item["category"].lower()
            outcome = item["outcome"].lower()
            if self._log_category not in {"", "all"}:
                if self._log_category == "error":
                    if item["severity"].upper() != "ERROR" and outcome != "failure":
                        continue
                elif category != self._log_category:
                    continue
            if self._log_outcome not in {"", "all"} and outcome != self._log_outcome:
                continue
            if self._log_chat and self._log_chat not in item["chatId"].lower():
                continue
            if self._log_operation and item["operationId"] != self._log_operation:
                continue
            if not _matches_query(
                item,
                self._log_query,
                aliases={
                    "severity": "severity",
                    "category": "category",
                    "outcome": "outcome",
                    "chat": "chatId",
                    "op": "operationId",
                    "operation": "operationId",
                    "action": "action",
                },
                free_fields=(
                    "action",
                    "category",
                    "outcome",
                    "chatId",
                    "operationId",
                    "severity",
                ),
            ):
                continue
            rows.append(item)
            if len(rows) >= 700:
                break
        self.logs_model.sync(rows)
        if self._selected_log and self.logs_model.find(self._selected_log) < 0:
            self._selected_log = ""
            self.selectionChanged.emit()
            self.detailsChanged.emit()
        self.stateChanged.emit()

    def _seed_fixture_runtime_logs(self) -> None:
        rows: list[dict[str, str]] = []
        sources = (
            ["server", "tunnel", "launcher", "audit", "desktop"]
            if self._runtime_log_source == "all"
            else [self._runtime_log_source]
        )
        now = datetime.now(timezone.utc)
        for source_index, source in enumerate(sources):
            for index in range(12):
                line = (
                    f"{now.isoformat()} [{source}] "
                    + (
                        "connector health check completed"
                        if index % 4
                        else "warning: fixture reconnect path exercised"
                    )
                )
                if self._runtime_log_query and self._runtime_log_query.lower() not in line.lower():
                    continue
                rows.append(
                    {
                        "rowId": f"fixture-runtime-{source}-{index}",
                        "source": source,
                        "timestamp": now.isoformat(),
                        "line": line,
                    }
                )
        self.runtime_logs_model.sync(rows)
        self._last_runtime_log_refresh_time = "12:35:00"
        self.stateChanged.emit()

    def _seed_fixture_doctor(self) -> None:
        checks = [
            {"name": "virtualenv", "status": "pass", "message": ".venv/bin/python"},
            {"name": "project_dependencies", "status": "pass", "message": "dependency closure healthy"},
            {"name": "config", "status": "warn", "message": "authentication disabled for fixture"},
            {"name": "server_process", "status": "pass", "message": "running · pid 208577"},
            {"name": "tunnel_process", "status": "pass", "message": "running · pid 15081"},
            {"name": "bridge_socket", "status": "pass", "message": "ready"},
            {"name": "local_rest", "status": "pass", "message": "HTTP 200"},
            {"name": "local_mcp", "status": "pass", "message": "initialize succeeded"},
            {"name": "public_auth", "status": "warn", "message": "public endpoint has REQUIRE_AUTH=false"},
        ]
        self._doctor = {
            "ok": True,
            "status": "degraded",
            "warning_count": 2,
            "failure_count": 0,
            "checks": checks,
            "config_checks": self.config_checks_model.rows(),
        }
        self.doctor_checks_model.sync(checks)
        self._doctor_busy = False
        self.stateChanged.emit()

    def _seed_fixture(self) -> None:
        self._selected_session = ""
        self._selected_operation = ""
        self._selected_log = ""
        self._status = {
            "ok": True,
            "bridge": "ready",
            "supervisor": {"running": True, "pid": 10421},
            "server": {"running": True, "pid": 208577},
            "tunnel": {"running": True, "pid": 15081},
            "url": "https://safe-ui-verification.example/mcp",
            "last_known_url": "https://safe-ui-verification.example/mcp",
            "url_state": "active",
            "connector_ready": True,
            "auth_required": False,
            "workspace": "/home/light/Workspace/Project/auto_download_ctf_challenge",
        }
        self._health = {
            "ok": True,
            "metrics": {
                "uptime_seconds": 18432,
                "total_requests": 1248,
                "error_count": 2,
                "client_error_count": 18,
                "auth_failures": 3,
                "rate_limit_hits": 0,
                "in_flight": 2,
                "peak_in_flight": 12,
                "p95_latency_ms": 48.2,
            },
            "capacity": {"commands": {"in_use": 2, "limit": 100}},
        }
        self._capabilities = {
            "version": "1.0.0",
            "host": {"command_policy": "guarded"},
            "limits": {
                "max_timeout_seconds": 300,
                "max_single_file_bytes": 3000000,
                "max_output_bytes": 500000,
                "max_concurrent_commands": 100,
            },
        }
        now = time.time()
        names = [
            "cw-20260830-botquanganh-mcp-ui-remake",
            "cw-20260830-auto-download-ctf-challenge",
            "cw-20260830-solve-ASIS-Another-Baby-Web-f031cb21",
            "cw-20260830-crypto-less-is-more",
            "cw-20260830-debug-center-state",
            "cw-20260830-research-qml-layout",
        ]
        self._sessions_all = [
            {
                "chatId": name,
                "displayName": name,
                "createdAt": now - (len(names) - index) * 7200,
                "lastChanged": now - index * 95,
                "sessionState": "RUNNING" if index == 2 else "enabled",
            }
            for index, name in enumerate(names)
        ]
        self._unread_by_session[names[1]] = 3
        self._unread_by_session[names[4]] = 1
        self._operations_all = []
        statuses = ["succeeded", "succeeded", "timed_out", "succeeded", "failed", "running"]
        commands = [
            "python solve.py --challenge another-baby",
            "git status --short",
            "ffuf -w paths.txt -u https://target/FUZZ",
            "python -m pytest -q tests/test_center_reducer.py",
            "python exploit.py --dry-run",
            "python scripts/verify_qml_ui.py --live-readonly",
        ]
        for index in range(24):
            status = statuses[index % len(statuses)]
            chat = names[2 if index < 18 else index % len(names)]
            record = {
                "operation_id": f"fixture-op-{index}",
                "event_id": f"fixture-event-{index}",
                "timestamp": datetime.fromtimestamp(now - index * 41, timezone.utc).isoformat(),
                "status": status,
                "activity_status": status,
                "command": commands[index % len(commands)],
                "chat_id": chat,
                "cwd": "/safe/workspace",
                "exit_code": 0 if status == "succeeded" else 1,
                "duration_ms": [16, 32, 24921, 50115, 120004][index % 5],
                "stdout": (
                    "verification output\n"
                    "/sys/kernel/tracing/events/sched/sched_process_exec/enable 400\n"
                    "all checks completed\n"
                ),
                "stderr": "fixture error detail\n" if status == "failed" else "",
            }
            self._operations_all.append(self._operation_row(record))
        self._logs_all = []
        for index in range(80):
            mapping = {
                "event_id": f"fixture-log-{index}",
                "ts": datetime.fromtimestamp(now - index * 9, timezone.utc).isoformat(),
                "severity_text": "ERROR" if index % 11 == 0 else "WARNING" if index % 7 == 0 else "INFO",
                "event_category": ["process", "file", "session", "api"][index % 4],
                "event_action": ["host_run_command", "host_read_file", "host_workspace_bind"][index % 3],
                "event_outcome": "failure" if index % 11 == 0 else "success",
                "chat_id": names[index % len(names)],
                "interaction_id": f"fixture-op-{index % 24}",
                "event_duration_ms": float(4 + index % 30),
                "payload": {"fixture": True, "index": index},
            }
            row = workspace_log_row_from_mapping(mapping)
            if row:
                self._logs_all.append(self._log_row(row))
        self._workspaces_all = [
            {
                "chatId": name,
                "label": name.replace("cw-20260830-", ""),
                "path": f"/safe/workspaces/{name}",
                "workspaceState": "active",
                "archived": False,
                "metaOk": True,
                "createdAt": datetime.fromtimestamp(now - (index + 1) * 7200, timezone.utc).isoformat(),
                "lastActive": datetime.fromtimestamp(now - index * 95, timezone.utc).isoformat(),
                "lastActiveEpoch": now - index * 95,
                "sizeBytes": 1048576 * (index + 1),
                "sizeText": f"{index + 1}.0 MiB",
                "events": 20 + index * 7,
                "operations": 8 + index * 3,
                "failures": 1 if index in {2, 4} else 0,
            }
            for index, name in enumerate(names)
        ]
        for index in range(2):
            archived_id = f"cw-2026082{8 + index}-archived-fixture-{index}"
            self._workspaces_all.append(
                {
                    "chatId": archived_id,
                    "label": f"archived-fixture-{index}",
                    "path": f"/safe/workspaces/.archive/{archived_id}",
                    "workspaceState": "archived",
                    "archived": True,
                    "metaOk": True,
                    "createdAt": datetime.fromtimestamp(now - 172800 - index * 3600, timezone.utc).isoformat(),
                    "lastActive": datetime.fromtimestamp(now - 86400 - index * 3600, timezone.utc).isoformat(),
                    "lastActiveEpoch": now - 86400 - index * 3600,
                    "sizeBytes": 0,
                    "sizeText": "archived",
                    "events": 42,
                    "operations": 18,
                    "failures": index,
                }
            )
        self._workspace_summary = workspace_summary(self._workspaces_all)
        config_checks = [
            {"name": "env_file", "status": "pass", "message": "/safe/repo/.env"},
            {"name": "workspace", "status": "pass", "message": self._status["workspace"]},
            {"name": "command_policy", "status": "pass", "message": "guarded"},
            {"name": "auth", "status": "warn", "message": "REQUIRE_AUTH=false in fixture"},
        ]
        fixture_values = {
            "REQUIRE_AUTH": "false",
            "GATEWAY_TOKEN": "",
            "HOST_RESTRICT_TO_WORKSPACE": "true",
            "HOST_CHAT_WORKSPACES": "true",
            "HOST_CHAT_ISOLATE": "false",
            "HOST_COMMAND_POLICY": "guarded",
            "ATTRIBUTION_MODE": "enforce",
        }
        self.config_checks_model.sync(config_checks)
        self.security_model.sync(security_posture(fixture_values))
        self._stream_state = "live"
        self._overall = overall_health(self._status, self._health, self._stream_state, config_checks)
        self.attention_model.sync(
            attention_items(self._status, self._health, self._stream_state, config_checks)
        )
        self.health_metrics_model.sync(health_metric_rows(self._health))
        self._last_refresh_time = "12:34:56"
        self._last_full_refresh_time = "12:34:56"
        self._last_refresh_error = ""
        self._rebuild_workspaces()
        self.recent_operations_model.sync(self._operations_all[:8])
        self._rebuild_sessions()
        self._rebuild_operations()
        self._rebuild_logs()
        self._seed_fixture_runtime_logs()
        self._seed_fixture_doctor()
        self.stateChanged.emit()

    def _set_toast(self, kind: str, text: str) -> None:
        self._toast_kind = kind
        self._toast_text = _single_line(text)
        self.toastChanged.emit()

    @Slot()
    def clearToast(self) -> None:
        if not self._toast_text:
            return
        self._toast_text = ""
        self.toastChanged.emit()

    def _save_window_state(self) -> None:
        try:
            self.window_state_store.save(self.window_state)
        except Exception as exc:
            self._set_toast("warning", f"UI state save failed: {exc}")

    @Slot()
    def shutdown(self) -> None:
        self.refresh_timer.stop()
        if self.log_thread is not None:
            thread = self.log_thread
            self.log_thread = None
            thread.stop()
            # The worker is daemon-backed; never block UI shutdown on a
            # synchronous HTTP read that may only wake at the next heartbeat.
            thread.wait(250)
