"""PySide Workspace Logs panel driven by the existing desktop presentation layer."""

from __future__ import annotations

from collections.abc import Callable, Iterator
import queue
import threading
from typing import Any

from app.cli.desktop_qt.widgets import InspectorFrame, SectionHeading, apply_button_variant
from app.cli.desktop_views.activity import ActivityNotification, clip_text
from app.cli.desktop_views.i18n import DesktopTranslator
from app.cli.desktop_views.workspace_logs import (
    WORKSPACE_LOG_CACHE_LIMIT,
    WORKSPACE_LOG_CHIP_KEYS,
    WORKSPACE_LOG_RECONNECT_SECONDS,
    WorkspaceLogRow,
    filter_workspace_log_rows,
    format_workspace_log_time,
    normalize_workspace_log_chip,
    parse_sse_lines,
    workspace_log_inspector_content,
    workspace_log_row_from_mapping,
)


class WorkspaceLogState:
    """Presentation state for a replayable workspace-log stream."""

    def __init__(
        self,
        on_new_activity: Callable[[ActivityNotification], None],
        translator: DesktopTranslator | None = None,
        on_status_change: Callable[[str], None] | None = None,
    ) -> None:
        self.on_new_activity = on_new_activity
        self.on_status_change = on_status_change or (lambda _state: None)
        self.translator = translator or DesktopTranslator()
        self.rows: list[WorkspaceLogRow] = []
        self.selected_id: str | None = None
        self.seen_event_ids: set[str] = set()
        self.seen_activity_ids: set[str] = set()
        self.suppress_replay_activity_notifications = False
        self.last_event_id: str | None = None
        self.connection_status = "connecting"
        self.connection_error = ""
        self.chip = "all"
        self.chat_filter = ""
        self.outcome = "all"

    def visible_rows(self) -> list[WorkspaceLogRow]:
        return list(
            reversed(
                filter_workspace_log_rows(
                    self.rows,
                    chip=self.chip,
                    chat_filter=self.chat_filter,
                    outcome=self.outcome,
                )[-200:]
            )
        )

    def accept_event(self, envelope: dict[str, Any]) -> None:
        data = envelope.get("data")
        row = workspace_log_row_from_mapping(data, event_id=str(envelope.get("id") or ""))
        if row is None:
            return
        seen_key = row.event_id or "|".join(
            (row.chat_id, row.interaction_id, row.phase, row.timestamp, row.action)
        )
        is_new = bool(seen_key) and seen_key not in self.seen_event_ids
        if seen_key:
            self.seen_event_ids.add(seen_key)
        notification_id = row.interaction_id or seen_key
        activity_key = f"{row.chat_id}|{notification_id}" if row.chat_id else notification_id
        is_new_activity = bool(activity_key) and activity_key not in self.seen_activity_ids
        if activity_key:
            self.seen_activity_ids.add(activity_key)
        if row.event_id:
            self.last_event_id = row.event_id
            self.rows = [item for item in self.rows if item.event_id != row.event_id]
        self.rows.append(row)
        self.rows = self.rows[-WORKSPACE_LOG_CACHE_LIMIT:]
        self.connection_status, self.connection_error = "live", ""
        self.on_status_change(self.connection_status)
        if is_new and is_new_activity and row.chat_id and not self.suppress_replay_activity_notifications:
            self.on_new_activity(ActivityNotification(row.chat_id, notification_id))

    def accept_control(self, envelope: dict[str, Any]) -> None:
        if envelope.get("event") == "stream_replay":
            data = envelope.get("data")
            phase = str(data.get("phase") or "") if isinstance(data, dict) else ""
            if phase == "start":
                self.suppress_replay_activity_notifications = bool(
                    data.get("baseline") if isinstance(data, dict) else False
                )
            elif phase == "complete":
                self.suppress_replay_activity_notifications = False
            return
        if envelope.get("event") != "stream_reset":
            return
        self.last_event_id = None
        self.selected_id = None
        self.rows = []
        self.connection_status, self.connection_error = "reset", ""
        self.on_status_change(self.connection_status)

    def set_connection(self, state: str, error: str = "") -> None:
        self.connection_status = state
        self.connection_error = clip_text(error, 160) if error else ""
        self.on_status_change(self.connection_status)

    def set_translator(self, translator: DesktopTranslator) -> None:
        self.translator = translator


class WorkspaceLogTableModel:
    """Small Qt model over the filtered, newest-first workspace-log rows."""

    HEADERS = ("Time", "Severity", "Category", "Action", "Outcome", "Duration", "Chat ID")
    HEADER_KEYS = (
        "workspace_logs.time",
        "workspace_logs.severity",
        "workspace_logs.category",
        "workspace_logs.action",
        "workspace_logs.outcome",
        "activity.milliseconds",
        "workspace_logs.chat_id",
    )

    def __new__(cls, QtCore: Any, state: WorkspaceLogState) -> Any:
        class _Model(QtCore.QAbstractTableModel):
            HEADERS = cls.HEADERS
            HEADER_KEYS = cls.HEADER_KEYS

            def __init__(self) -> None:
                super().__init__()
                self.QtCore = QtCore
                self.state = state

            def rowCount(self, parent: Any = None) -> int:
                return 0 if parent and parent.isValid() else len(self.state.visible_rows())

            def columnCount(self, parent: Any = None) -> int:
                return 0 if parent and parent.isValid() else len(self.HEADERS)

            def data(self, index: Any, role: int = 0) -> Any:
                if not index.isValid() or role != self.QtCore.Qt.DisplayRole:
                    return None
                row = self.state.visible_rows()[index.row()]
                values = (
                    format_workspace_log_time(row.timestamp),
                    row.severity,
                    row.category,
                    clip_text(row.action, 42),
                    row.outcome,
                    f"{row.duration_ms:.3f}" if row.duration_ms is not None else "-",
                    clip_text(row.chat_id, 36),
                )
                return values[index.column()]

            def headerData(self, section: int, orientation: int, role: int = 0) -> Any:
                if orientation == self.QtCore.Qt.Horizontal and role == self.QtCore.Qt.DisplayRole:
                    return self.state.translator.text(self.HEADER_KEYS[section])
                return None

        return _Model()


class QtWorkspaceLogsPanel:
    """Qt controls and queue lifecycle for workspace-log presentation state."""

    def __init__(
        self,
        QtCore: Any,
        QtWidgets: Any,
        translator: DesktopTranslator | None = None,
        *,
        on_new_activity: Callable[[ActivityNotification], None] | None = None,
        stream_reader: Callable[[str | None], Iterator[dict[str, Any]]] | None = None,
        on_message: Callable[[str, str], None] | None = None,
        on_status_change: Callable[[str], None] | None = None,
    ) -> None:
        self.QtCore, self.QtWidgets = QtCore, QtWidgets
        self.translator = translator or DesktopTranslator()
        self.on_message = on_message or (lambda _kind, _message: None)
        self.state = WorkspaceLogState(
            on_new_activity or (lambda _notice: None), self.translator, on_status_change
        )
        self.stream_reader = stream_reader
        self.closed = False
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.event_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.widget = QtWidgets.QWidget()
        self.widget.setObjectName("workspaceLogsPage")
        self.model = WorkspaceLogTableModel(QtCore, self.state)
        self._build()
        self.drain_timer = QtCore.QTimer(self.widget)
        self.drain_timer.setInterval(50)
        self.drain_timer.timeout.connect(self._drain_queue)

    def _build(self) -> None:
        layout = self.QtWidgets.QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.page_heading = SectionHeading(
            self.QtWidgets,
            self.translator.text("nav.workspace_logs"),
        )
        self.page_heading.widget.setObjectName("pageHeader")
        self.heading = self.page_heading.title_label
        self.heading.setObjectName("workspaceLogsHeading")
        self.heading.setProperty("role", "pageTitle")
        self.page_title_label = self.heading
        self.page_subtitle_label = self.QtWidgets.QLabel()
        self.page_subtitle_label.setProperty("role", "pageSubtitle")
        self.page_heading.widget.layout().addWidget(self.page_subtitle_label)
        self.event_count_label = self.page_subtitle_label
        self.notice_label = self.event_count_label
        layout.addWidget(self.page_heading.widget)

        self.toolbar_frame = self.QtWidgets.QFrame()
        self.toolbar_frame.setObjectName("denseToolbar")
        self.toolbar_frame.setProperty("role", "card")
        self.toolbar_frame.setFixedHeight(48)
        toolbar = self.QtWidgets.QHBoxLayout(self.toolbar_frame)
        toolbar.setContentsMargins(10, 6, 10, 6)
        toolbar.setSpacing(6)
        self.chip_buttons: dict[str, Any] = {}
        for key in WORKSPACE_LOG_CHIP_KEYS:
            button = self.QtWidgets.QPushButton(self.translator.text(f"workspace_logs.{key}"))
            button.clicked.connect(lambda _checked=False, key=key: self.select_chip(key))
            button.setProperty("role", "compactAction")
            self.chip_buttons[key] = button
            toolbar.addWidget(button)
        toolbar.addSpacing(4)
        self.chat_filter_label = self.QtWidgets.QLabel(
            self.translator.text("field.chat_filter")
        )
        toolbar.addWidget(self.chat_filter_label)
        self.chat_filter_input = self.QtWidgets.QLineEdit()
        self.chat_filter_input.setClearButtonEnabled(True)
        self.chat_filter_input.textChanged.connect(self._set_chat_filter)
        toolbar.addWidget(self.chat_filter_input, 1)
        self.outcome_combo = self.QtWidgets.QComboBox()
        self.outcome_combo.addItems(("all", "success", "failure", "unknown"))
        self.outcome_combo.currentTextChanged.connect(self._set_outcome)
        toolbar.addWidget(self.outcome_combo)
        self.clear_button = self.QtWidgets.QPushButton(self.translator.text("action.clear"))
        self.clear_button.clicked.connect(self.clear_filters)
        self.clear_button.setProperty("role", "compactAction")
        apply_button_variant(self.clear_button, "secondary")
        toolbar.addWidget(self.clear_button)
        layout.addWidget(self.toolbar_frame)

        self.content_splitter = self.QtWidgets.QSplitter(self.QtCore.Qt.Horizontal)
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.setHandleWidth(8)
        self.table_frame = self.QtWidgets.QFrame()
        self.table_frame.setObjectName("workspaceLogsTableFrame")
        self.table_frame.setProperty("role", "card")
        table_layout = self.QtWidgets.QVBoxLayout(self.table_frame)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)
        self.table = self.QtWidgets.QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(self.QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(self.QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setHorizontalScrollBarPolicy(self.QtCore.Qt.ScrollBarAlwaysOff)
        self.table.selectionModel().selectionChanged.connect(self._show_selected)
        table_header = self.table.horizontalHeader()
        table_header.setStretchLastSection(False)
        table_widths = (132, 62, 74, 160, 72, 62, 110)
        for section, width in enumerate(table_widths):
            table_header.setSectionResizeMode(
                section, self.QtWidgets.QHeaderView.Fixed
            )
            table_header.resizeSection(section, width)
        table_header.setSectionResizeMode(3, self.QtWidgets.QHeaderView.Stretch)
        table_layout.addWidget(self.table)
        self.content_splitter.addWidget(self.table_frame)

        self.inspector_panel = InspectorFrame(
            self.QtWidgets, self.translator.text("workspace_logs.inspector")
        )
        self.inspector_frame = self.inspector_panel.widget
        self.inspector_frame.setObjectName("workspaceLogsInspectorFrame")
        self.inspector_frame.setProperty("role", "inspectorSurface")
        inspector_layout = self.inspector_panel.layout
        self.inspector_heading = self.inspector_panel.title
        self.inspector_detail_grid = self.QtWidgets.QFrame()
        self.inspector_detail_grid.setObjectName("workspaceInspectorDetailGrid")
        detail_grid = self.QtWidgets.QGridLayout(self.inspector_detail_grid)
        detail_grid.setContentsMargins(10, 8, 10, 8)
        detail_grid.setHorizontalSpacing(10)
        detail_grid.setVerticalSpacing(4)
        self.inspector_detail_name_labels: dict[str, Any] = {}
        self.inspector_detail_values: dict[str, Any] = {}
        for position, (key, label_key) in enumerate(
            (
                ("action", "workspace_logs.action"),
                ("outcome", "workspace_logs.outcome"),
                ("severity", "workspace_logs.severity"),
                ("duration", "workspace_logs.detail.duration"),
            )
        ):
            name = self.QtWidgets.QLabel(self.translator.text(label_key).split(":")[0])
            name.setProperty("role", "detailLabel")
            value = self.QtWidgets.QLabel("—")
            value.setProperty("role", "inspectorValue")
            row, column = divmod(position, 2)
            detail_grid.addWidget(name, row, column * 2)
            detail_grid.addWidget(value, row, column * 2 + 1)
            self.inspector_detail_name_labels[key] = name
            self.inspector_detail_values[key] = value
        inspector_layout.addWidget(self.inspector_detail_grid)
        self.inspector = self.QtWidgets.QTabWidget()
        self.inspector_views: dict[str, Any] = {}
        for key, label_key in (("summary", "workspace_logs.summary"), ("metadata", "workspace_logs.metadata"), ("payload", "workspace_logs.payload")):
            view = self.QtWidgets.QPlainTextEdit()
            view.setObjectName("workspaceInspectorView")
            view.setReadOnly(True)
            self.inspector.addTab(view, self.translator.text(label_key))
            self.inspector_views[key] = view
        inspector_layout.addWidget(self.inspector, 1)
        self.content_splitter.addWidget(self.inspector_frame)
        self.content_splitter.setStretchFactor(0, 68)
        self.content_splitter.setStretchFactor(1, 32)
        self.content_splitter.setSizes((680, 320))
        layout.addWidget(self.content_splitter, 1)
        self._restyle_chips()
        self.render()

    def _notice(self) -> str:
        visible = len(self.state.visible_rows())
        state_key = {
            "live": "workspace_logs.state.live",
            "reconnecting": "workspace_logs.state.reconnecting",
            "reset": "workspace_logs.state.reset",
        }.get(self.state.connection_status, "workspace_logs.state.connecting")
        error = f" · {self.state.connection_error}" if self.state.connection_error else ""
        if visible:
            return self.translator.text("workspace_logs.notice", state=self.translator.text(state_key), visible=visible, cached=len(self.state.rows), error=error)
        return self.translator.text("workspace_logs.notice_empty", state=self.translator.text(state_key), empty=self.translator.text("workspace_logs.empty"), cached=len(self.state.rows), error=error)

    def render(self) -> None:
        self.model.layoutChanged.emit()
        self.notice_label.setText(self._notice())
        rows = self.state.visible_rows()
        selected = next((index for index, row in enumerate(rows) if row.event_id == self.state.selected_id), None)
        if selected is not None:
            self.table.selectRow(selected)
        elif rows:
            self.table.selectRow(0)
        else:
            for view in self.inspector_views.values():
                view.setPlainText("")
            for value in self.inspector_detail_values.values():
                value.setText("—")

    def select_chip(self, key: str) -> None:
        normalized = normalize_workspace_log_chip(key)
        if normalized is None or normalized == self.state.chip:
            return
        self.state.chip = normalized
        self._restyle_chips()
        self.render()

    def _restyle_chips(self) -> None:
        for key, button in self.chip_buttons.items():
            apply_button_variant(button, "primary" if key == self.state.chip else "secondary")

    def _set_chat_filter(self, value: str) -> None:
        self.state.chat_filter = value
        self.render()

    def _set_outcome(self, value: str) -> None:
        self.state.outcome = value
        self.render()

    def clear_filters(self) -> None:
        self.state.chip, self.state.chat_filter, self.state.outcome = "all", "", "all"
        self.chat_filter_input.setText("")
        self.outcome_combo.setCurrentText("all")
        self._restyle_chips()
        self.render()

    def _show_selected(self, *_args: Any) -> None:
        index = self.table.currentIndex()
        rows = self.state.visible_rows()
        if not index.isValid() or index.row() >= len(rows):
            return
        row = rows[index.row()]
        self.state.selected_id = row.event_id or None
        detail_values = {
            "action": row.action or "—",
            "outcome": row.outcome,
            "severity": row.severity,
            "duration": (
                f"{row.duration_ms:.1f} ms" if row.duration_ms is not None else "—"
            ),
        }
        for key, value in detail_values.items():
            self.inspector_detail_values[key].setText(value)
        for key, content in workspace_log_inspector_content(row, self.translator).items():
            self.inspector_views[key].setPlainText(content)

    def set_translator(self, translator: DesktopTranslator) -> None:
        self.translator = translator
        self.state.set_translator(translator)
        self.heading.setText(translator.text("nav.workspace_logs"))
        for key, button in self.chip_buttons.items():
            button.setText(translator.text(f"workspace_logs.{key}"))
        self.chat_filter_label.setText(translator.text("field.chat_filter"))
        self.clear_button.setText(translator.text("action.clear"))
        self.inspector_heading.setText(translator.text("workspace_logs.inspector"))
        for index, label_key in enumerate(("workspace_logs.summary", "workspace_logs.metadata", "workspace_logs.payload")):
            self.inspector.setTabText(index, translator.text(label_key))
        self.model.headerDataChanged.emit(
            self.QtCore.Qt.Horizontal, 0, len(self.model.HEADERS) - 1
        )
        self.render()

    def start_stream(self) -> None:
        if self.thread is not None or self.stream_reader is None or self.closed:
            return
        self.drain_timer.start()

        def worker() -> None:
            while not self.stop_event.is_set():
                try:
                    self.event_queue.put(("connection", ("connecting", "")))
                    for envelope in self.stream_reader(self.state.last_event_id):
                        if self.stop_event.is_set() or self.closed:
                            return
                        self.event_queue.put(("event" if envelope.get("event") == "workspace_log" else "control", envelope))
                    if self.stop_event.is_set() or self.closed:
                        return
                    self.event_queue.put(("connection", ("reconnecting", "")))
                except Exception as exc:
                    if self.stop_event.is_set() or self.closed:
                        return
                    self.event_queue.put(("connection", ("reconnecting", f"{type(exc).__name__}: {exc}")))
                if self.stop_event.wait(WORKSPACE_LOG_RECONNECT_SECONDS):
                    return

        self.thread = threading.Thread(target=worker, name="bqa-qt-workspace-logs", daemon=True)
        self.thread.start()

    def _drain_queue(self) -> None:
        while not self.closed:
            try:
                kind, payload = self.event_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "event":
                self.state.accept_event(payload)
            elif kind == "control":
                self.state.accept_control(payload)
            elif kind == "connection":
                self.state.set_connection(*payload)
            self.render()

    def close(self) -> None:
        self.closed = True
        self.stop_event.set()
        self.drain_timer.stop()
