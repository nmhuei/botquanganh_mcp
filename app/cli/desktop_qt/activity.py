"""PySide GPT activity panel using the existing desktop activity presentation."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from PySide6 import QtGui

from app.cli.desktop_qt.widgets import InspectorFrame
from app.cli.desktop_views.activity import (
    ActivityNotification,
    WorkspaceSession,
    activity_status_label,
    clip_text,
    command_activity_inspector_content,
    filter_activity_records_for_session,
    format_stream_time,
    project_command_activity_records,
)
from app.cli.desktop_views.i18n import DesktopTranslator


class ActivityState:
    """Local-only activity controls and snapshots for the Qt presentation."""

    def __init__(
        self,
        workspace_root: Callable[[], Any],
        translator: DesktopTranslator | None = None,
    ) -> None:
        self.workspace_root = workspace_root
        self.translator = translator or DesktopTranslator()
        self.sessions: list[WorkspaceSession] = []
        self.session_order_ids: list[str] = []
        self.records: list[dict[str, Any]] = []
        self.running_session_ids: set[str] = set()
        self.visible_session_ids: set[str] = set()
        self.closed_session_ids: set[str] = set()
        self.disabled_session_ids: set[str] = set()
        self.session_selected_id: str | None = None
        self.seen_event_ids: set[str] = set()
        self.activity_snapshot_loaded = False
        self.command_filter = ""
        self.workplace_filter = ""
        self.sort_key: str | None = None
        self.sort_descending = False

    def refresh(
        self,
        sessions: Sequence[WorkspaceSession],
        records: Sequence[dict[str, Any]],
    ) -> set[ActivityNotification]:
        sessions_by_id = {session.chat_id: session for session in sessions}
        retained = [chat_id for chat_id in self.session_order_ids if chat_id in sessions_by_id]
        retained_set = set(retained)
        self.session_order_ids = retained + [
            session.chat_id for session in sessions if session.chat_id not in retained_set
        ]
        self.sessions = [sessions_by_id[chat_id] for chat_id in self.session_order_ids]
        self.records = project_command_activity_records(records)
        self.running_session_ids = {
            str(record["chat_id"])
            for record in self.records
            if record.get("is_running") and record.get("chat_id")
        }
        available = set(sessions_by_id)
        self.visible_session_ids.intersection_update(available)
        self.closed_session_ids.intersection_update(available)
        self.disabled_session_ids.intersection_update(available)
        if self.session_selected_id not in available or self.session_selected_id in self.closed_session_ids:
            self.session_selected_id = None
        notices: set[ActivityNotification] = set()
        for record in self.records:
            event_id = str(record.get("event_id") or "")
            activity_id = str(record.get("operation_id") or event_id)
            if not activity_id or activity_id in self.seen_event_ids:
                continue
            self.seen_event_ids.add(activity_id)
            chat_id = str(record.get("chat_id") or "")
            if self.activity_snapshot_loaded and chat_id:
                notices.add(ActivityNotification(chat_id, activity_id))
        self.activity_snapshot_loaded = True
        return notices

    def reveal_session(self, chat_id: str) -> bool:
        if not chat_id:
            return False
        self.closed_session_ids.discard(chat_id)
        self.visible_session_ids.add(chat_id)
        return True

    def activate_session(self, chat_id: str) -> bool:
        if not self.reveal_session(chat_id):
            return False
        if self.workplace_filter and self.workplace_filter.lower() not in chat_id.lower():
            self.workplace_filter = ""
        self.disabled_session_ids.discard(chat_id)
        self.session_selected_id = chat_id
        return True

    def show_all_sessions(self) -> None:
        self.session_selected_id = None

    def enable_session(self, chat_id: str) -> bool:
        if not chat_id:
            return False
        self.disabled_session_ids.discard(chat_id)
        self.session_selected_id = chat_id
        return True

    def disable_session(self, chat_id: str) -> bool:
        if not chat_id:
            return False
        self.disabled_session_ids.add(chat_id)
        self.session_selected_id = chat_id
        return True

    def close_session(self, chat_id: str) -> bool:
        if not chat_id:
            return False
        self.closed_session_ids.add(chat_id)
        self.visible_session_ids.discard(chat_id)
        self.disabled_session_ids.discard(chat_id)
        if self.session_selected_id == chat_id:
            self.session_selected_id = None
        return True

    def filtered_sessions(self) -> list[WorkspaceSession]:
        needle = self.workplace_filter.strip().lower()
        return [
            session
            for session in self.sessions
            if session.chat_id in self.visible_session_ids
            and session.chat_id not in self.closed_session_ids
            and needle in session.chat_id.lower()
        ]

    def filtered_records(self) -> list[dict[str, Any]]:
        selected = filter_activity_records_for_session(self.records, self.session_selected_id)
        needle = self.command_filter.strip().lower()
        if needle:
            selected = [
                record
                for record in selected
                if needle
                in " ".join(
                    str(record.get(key) or "")
                    for key in ("command", "chat_id", "activity_status", "stdout", "stderr")
                ).lower()
            ]
        if self.sort_key is not None:
            record_key = {
                "time": "timestamp",
                "workplace": "chat_id",
                "status": "activity_status",
                "exit": "exit_code",
                "duration": "duration_ms",
            }.get(self.sort_key, self.sort_key)
            selected = sorted(
                selected,
                key=lambda record: str(record.get(record_key) or ""),
                reverse=self.sort_descending,
            )
        return selected


class ActivitySessionModel:
    """Qt model over activity workplaces visible in the session rail."""

    HEADERS = ("SESSION", "STATE", "LAST")

    def __new__(cls, QtCore: Any, state: ActivityState) -> Any:
        class _Model(QtCore.QAbstractTableModel):
            HEADERS = cls.HEADERS

            def rowCount(self, parent: Any = None) -> int:
                return 0 if parent and parent.isValid() else len(state.filtered_sessions())

            def columnCount(self, parent: Any = None) -> int:
                return 0 if parent and parent.isValid() else len(self.HEADERS)

            def data(self, index: Any, role: int = 0) -> Any:
                if not index.isValid() or role not in (
                    QtCore.Qt.DisplayRole,
                    QtCore.Qt.ToolTipRole,
                ):
                    return None
                session = state.filtered_sessions()[index.row()]
                status = (
                    state.translator.text("activity.running")
                    if session.chat_id in state.running_session_ids
                    else state.translator.text("status.disabled")
                    if session.chat_id in state.disabled_session_ids
                    else state.translator.text("status.enabled")
                )
                stream_time = format_stream_time(session.last_changed).split(" ")[-1]
                full_values = (session.chat_id, status, stream_time)
                if role == QtCore.Qt.ToolTipRole:
                    return full_values[index.column()]
                display_values = (clip_text(session.chat_id, 26), status, stream_time)
                return display_values[index.column()]

            def headerData(self, section: int, orientation: int, role: int = 0) -> Any:
                if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
                    return state.translator.text(("activity.session", "activity.state", "activity.last")[section])
                return None

        return _Model()


class ActivityCommandModel:
    """Qt model over projected command activity."""

    HEADERS = ("UTC", "Workplace", "Status", "Command input", "Exit", "ms")
    HEADER_KEYS = (
        "activity.utc", "activity.workplace", "activity.status", "activity.command_input",
        "activity.exit", "activity.milliseconds",
    )

    def __new__(cls, QtCore: Any, state: ActivityState) -> Any:
        class _Model(QtCore.QAbstractTableModel):
            HEADERS = cls.HEADERS

            def rowCount(self, parent: Any = None) -> int:
                return 0 if parent and parent.isValid() else len(state.filtered_records())

            def columnCount(self, parent: Any = None) -> int:
                return 0 if parent and parent.isValid() else len(self.HEADERS)

            def data(self, index: Any, role: int = 0) -> Any:
                if not index.isValid() or role != QtCore.Qt.DisplayRole:
                    return None
                record = state.filtered_records()[index.row()]
                status = str(record.get("activity_status") or "failed")
                values = (
                    str(record.get("timestamp", "")).replace("T", " ").replace("+00:00", "Z"),
                    clip_text(record.get("chat_id") or "shared", 28),
                    activity_status_label(status, state.translator),
                    clip_text(record.get("command", ""), 84),
                    "-" if status == "running" else str(record.get("exit_code", "-")),
                    str(record.get("duration_ms", "-")),
                )
                return values[index.column()]

            def headerData(self, section: int, orientation: int, role: int = 0) -> Any:
                if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
                    return state.translator.text(cls.HEADER_KEYS[section])
                return None

        return _Model()


class QtActivityPanel:
    """Standalone, presentation-only Qt activity panel."""

    def __init__(self, QtCore: Any, QtWidgets: Any, workspace_root: Callable[[], Any], translator: DesktopTranslator | None = None) -> None:
        self.QtCore, self.QtWidgets = QtCore, QtWidgets
        self.state = ActivityState(workspace_root, translator)
        self.widget = QtWidgets.QWidget()
        self.widget.setObjectName("activityPage")
        self.session_model = ActivitySessionModel(QtCore, self.state)
        self.command_model = ActivityCommandModel(QtCore, self.state)
        self.selected_command_id: str | None = None
        self.input_collapsed = False
        self.output_collapsed = False
        self._investigation_splitter_sizes: list[int] | None = None
        self._command_scroll_restore_generation = 0
        self._editor_scroll_restore_generations: dict[int, int] = {}
        self._editor_pending_scroll_positions: dict[int, tuple[int, int]] = {}
        self._inspected_command_id: str | None = None
        self._build()

    def _build(self) -> None:
        layout = self.QtWidgets.QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.page_heading = self.QtWidgets.QFrame()
        self.page_heading.setObjectName("pageHeader")
        self.page_heading.setSizePolicy(
            self.QtWidgets.QSizePolicy.Expanding,
            self.QtWidgets.QSizePolicy.Fixed,
        )
        page_heading_layout = self.QtWidgets.QVBoxLayout(self.page_heading)
        page_heading_layout.setContentsMargins(0, 0, 0, 0)
        page_heading_layout.setSpacing(2)
        self.page_title_label = self.QtWidgets.QLabel(
            self.state.translator.text("nav.gpt_activity")
        )
        self.page_title_label.setProperty("role", "pageTitle")
        self.page_subtitle_label = self.QtWidgets.QLabel()
        self.page_subtitle_label.setProperty("role", "pageSubtitle")
        page_heading_layout.addWidget(self.page_title_label)
        page_heading_layout.addWidget(self.page_subtitle_label)
        layout.addWidget(self.page_heading)
        self.content_splitter = self.QtWidgets.QSplitter(self.QtCore.Qt.Horizontal)
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.setHandleWidth(8)
        layout.addWidget(self.content_splitter)

        self.session_rail = self.QtWidgets.QFrame()
        self.session_rail.setObjectName("activitySessionRail")
        self.session_rail.setProperty("role", "card")
        self.session_rail.setFixedWidth(260)
        rail_layout = self.QtWidgets.QVBoxLayout(self.session_rail)
        rail_layout.setContentsMargins(12, 12, 12, 12)
        rail_layout.setSpacing(8)
        self.session_heading = self.QtWidgets.QLabel(
            self.state.translator.text("activity.workplaces")
        )
        self.session_heading.setProperty("role", "sectionEyebrow")
        rail_layout.addWidget(self.session_heading)
        self.session_source = self.QtWidgets.QLabel(
            self.state.translator.text("activity.folder_source")
        )
        self.session_source.setWordWrap(True)
        self.session_source.setProperty("role", "footerStatus")
        rail_layout.addWidget(self.session_source)
        self.workplace_filter_input = self.QtWidgets.QLineEdit()
        self.workplace_filter_input.setPlaceholderText(self.state.translator.text("field.chat_filter"))
        self.workplace_filter_input.setClearButtonEnabled(True)
        self.workplace_filter_input.textChanged.connect(self._set_workplace_filter)
        rail_layout.addWidget(self.workplace_filter_input)
        self.session_notice = self.QtWidgets.QLabel()
        self.session_notice.setProperty("role", "footerStatus")
        self.session_notice.setWordWrap(True)
        rail_layout.addWidget(self.session_notice)
        self.sessions_table = self.QtWidgets.QTableView()
        self.sessions_table.setModel(self.session_model)
        self.sessions_table.setSelectionBehavior(self.QtWidgets.QAbstractItemView.SelectRows)
        self.sessions_table.setSelectionMode(self.QtWidgets.QAbstractItemView.SingleSelection)
        self.sessions_table.setAlternatingRowColors(True)
        self.sessions_table.verticalHeader().setDefaultSectionSize(28)
        self.sessions_table.verticalHeader().hide()
        self.sessions_table.setHorizontalScrollBarPolicy(
            self.QtCore.Qt.ScrollBarAlwaysOff
        )
        session_header = self.sessions_table.horizontalHeader()
        session_header.setStretchLastSection(False)
        for section, width in enumerate((91, 70, 71)):
            session_header.setSectionResizeMode(
                section, self.QtWidgets.QHeaderView.Fixed
            )
            session_header.resizeSection(section, width)
        self.sessions_table.selectionModel().selectionChanged.connect(self._select_session)
        rail_layout.addWidget(self.sessions_table, 1)
        session_actions = self.QtWidgets.QGridLayout()
        session_actions.setHorizontalSpacing(6)
        session_actions.setVerticalSpacing(6)
        for index, (key, callback) in enumerate((("action.all", self.show_all_sessions), ("action.enable_tracking", self._enable_selected), ("action.disable_tracking", self._disable_selected), ("action.close_tab", self._close_selected))):
            button = self.QtWidgets.QPushButton(self.state.translator.text(key))
            button.clicked.connect(callback)
            button.setProperty("role", "compactAction")
            session_actions.addWidget(button, index // 2, index % 2)
            setattr(self, f"_{key.split('.')[-1]}_button", button)
        rail_layout.addLayout(session_actions)
        self.content_splitter.addWidget(self.session_rail)

        self.activity_main = self.QtWidgets.QWidget()
        main_layout = self.QtWidgets.QVBoxLayout(self.activity_main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)
        self.command_toolbar = self.QtWidgets.QFrame()
        self.command_toolbar.setObjectName("activityCommandToolbar")
        self.command_toolbar.setProperty("role", "card")
        self.command_toolbar.setFixedHeight(48)
        toolbar = self.QtWidgets.QHBoxLayout(self.command_toolbar)
        toolbar.setContentsMargins(12, 8, 12, 8)
        toolbar.setSpacing(8)
        self.command_filter_input = self.QtWidgets.QLineEdit()
        self.command_filter_input.setPlaceholderText(self.state.translator.text("activity.command_input"))
        self.command_filter_input.setClearButtonEnabled(True)
        self.command_filter_input.textChanged.connect(self._set_command_filter)
        toolbar.addWidget(self.command_filter_input, 1)
        self.clear_button = self.QtWidgets.QPushButton(self.state.translator.text("action.clear"))
        self.clear_button.clicked.connect(self.clear_filters)
        self.clear_button.setProperty("role", "compactAction")
        toolbar.addWidget(self.clear_button)
        self.copy_tab_button = self.QtWidgets.QPushButton(self.state.translator.text("action.copy_tab"))
        self.copy_tab_button.clicked.connect(self.copy_active_tab)
        self.copy_tab_button.setProperty("role", "compactAction")
        toolbar.addWidget(self.copy_tab_button)
        self.filter_summary = self.QtWidgets.QLabel()
        self.filter_summary.setProperty("role", "footerStatus")
        toolbar.addWidget(self.filter_summary)
        main_layout.addWidget(self.command_toolbar)

        self.activity_workbench_splitter = self.QtWidgets.QSplitter(
            self.QtCore.Qt.Vertical
        )
        self.activity_workbench_splitter.setObjectName("activityWorkbenchSplitter")
        self.activity_workbench_splitter.setChildrenCollapsible(False)
        self.activity_workbench_splitter.setHandleWidth(8)

        self.investigation_controls = self.QtWidgets.QFrame()
        self.investigation_controls.setObjectName("activityInvestigationControls")
        self.investigation_controls.setProperty("role", "card")
        investigation_controls_layout = self.QtWidgets.QHBoxLayout(
            self.investigation_controls
        )
        investigation_controls_layout.setContentsMargins(12, 6, 12, 6)
        investigation_controls_layout.setSpacing(8)
        investigation_controls_layout.addStretch(1)
        self.input_toggle = self.QtWidgets.QPushButton()
        self.input_toggle.clicked.connect(self.toggle_input_panel)
        self.input_toggle.setFocusPolicy(self.QtCore.Qt.StrongFocus)
        self.input_toggle.setProperty("role", "compactAction")
        self.input_collapse_button = self.input_toggle
        investigation_controls_layout.addWidget(self.input_toggle)
        self.output_toggle = self.QtWidgets.QPushButton()
        self.output_toggle.clicked.connect(self.toggle_output_panel)
        self.output_toggle.setFocusPolicy(self.QtCore.Qt.StrongFocus)
        self.output_toggle.setProperty("role", "compactAction")
        self.output_collapse_button = self.output_toggle
        investigation_controls_layout.addWidget(self.output_toggle)
        self.investigation_splitter = self.QtWidgets.QSplitter(
            self.QtCore.Qt.Horizontal
        )
        self.investigation_splitter.setObjectName("activityInvestigationSplitter")
        self.investigation_splitter.setChildrenCollapsible(False)
        self.investigation_splitter.setHandleWidth(8)
        self.vertical_splitter = self.investigation_splitter
        self.command_frame = self.QtWidgets.QFrame()
        self.command_frame.setObjectName("activityCommandFrame")
        self.command_frame.setProperty("role", "card")
        input_layout = self.QtWidgets.QVBoxLayout(self.command_frame)
        input_layout.setContentsMargins(12, 10, 12, 12)
        input_layout.setSpacing(8)
        self.command_heading = self.QtWidgets.QLabel(
            self.state.translator.text("activity.commands")
        )
        self.command_heading.setProperty("role", "sectionEyebrow")
        input_layout.addWidget(self.command_heading)
        self.command_table = self.QtWidgets.QTableView()
        self.command_table.setModel(self.command_model)
        self.command_table.setSelectionBehavior(self.QtWidgets.QAbstractItemView.SelectRows)
        self.command_table.setSelectionMode(self.QtWidgets.QAbstractItemView.SingleSelection)
        self.command_table.setAlternatingRowColors(True)
        self.command_table.verticalHeader().setDefaultSectionSize(30)
        self.command_table.verticalHeader().hide()
        self.command_table.setHorizontalScrollBarPolicy(
            self.QtCore.Qt.ScrollBarAlwaysOff
        )
        self.command_table.selectionModel().selectionChanged.connect(self._show_selected_command)
        self.command_table.horizontalHeader().sectionClicked.connect(self._sort_records)
        command_header = self.command_table.horizontalHeader()
        command_header.setStretchLastSection(False)
        for section, width in enumerate((142, 108, 70, 250, 48, 48)):
            command_header.setSectionResizeMode(
                section, self.QtWidgets.QHeaderView.Fixed
            )
            command_header.resizeSection(section, width)
        command_header.setSectionResizeMode(3, self.QtWidgets.QHeaderView.Stretch)
        input_layout.addWidget(self.command_table)

        self.input_inspector_panel = InspectorFrame(
            self.QtWidgets, self.state.translator.text("action.input")
        )
        self.input_panel = self.input_inspector_panel.widget
        self.input_panel.setObjectName("activityInputSurface")
        self.input_heading = self.input_inspector_panel.title
        self.command_input_view = self.QtWidgets.QPlainTextEdit()
        self.command_input_view.setObjectName("activityCommandInput")
        self.command_input_view.setReadOnly(True)
        self.command_input_view.setLineWrapMode(
            self.QtWidgets.QPlainTextEdit.WidgetWidth
        )
        self.command_input_view.setWordWrapMode(
            QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere
        )
        self.command_input_view.setHorizontalScrollBarPolicy(
            self.QtCore.Qt.ScrollBarAlwaysOff
        )
        self.command_input_view.setVerticalScrollBarPolicy(
            self.QtCore.Qt.ScrollBarAsNeeded
        )
        self.input_inspector_panel.layout.addWidget(self.command_input_view, 1)
        self.investigation_splitter.addWidget(self.input_panel)

        self.inspector_panel = InspectorFrame(
            self.QtWidgets, self.state.translator.text("activity.output")
        )
        self.inspector_frame = self.inspector_panel.widget
        self.inspector_frame.setProperty("role", "inspectorSurface")
        self.output_panel = self.inspector_frame
        output_layout = self.inspector_panel.layout
        self.inspector_heading = self.inspector_panel.title
        self.inspector = self.QtWidgets.QTabWidget()
        self.inspector_views: dict[str, Any] = {}
        for key, label_key in (("metadata", "activity.metadata"), ("stdout", "activity.stdout"), ("stderr", "activity.stderr"), ("human", "activity.human")):
            view = self.QtWidgets.QPlainTextEdit()
            view.setReadOnly(True)
            view.setLineWrapMode(self.QtWidgets.QPlainTextEdit.WidgetWidth)
            view.setWordWrapMode(QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
            view.setHorizontalScrollBarPolicy(self.QtCore.Qt.ScrollBarAlwaysOff)
            view.setVerticalScrollBarPolicy(self.QtCore.Qt.ScrollBarAsNeeded)
            self.inspector.addTab(view, self.state.translator.text(label_key))
            self.inspector_views[key] = view
        output_layout.addWidget(self.inspector, 1)
        self.investigation_splitter.addWidget(self.inspector_frame)
        self.investigation_splitter.setStretchFactor(0, 1)
        self.investigation_splitter.setStretchFactor(1, 1)
        self.investigation_splitter.setSizes((360, 360))

        self.inspection_workspace = self.QtWidgets.QWidget()
        self.inspection_workspace.setObjectName("activityInspectionWorkspace")
        inspection_workspace_layout = self.QtWidgets.QVBoxLayout(
            self.inspection_workspace
        )
        inspection_workspace_layout.setContentsMargins(0, 0, 0, 0)
        inspection_workspace_layout.setSpacing(8)
        inspection_workspace_layout.addWidget(self.investigation_controls)
        inspection_workspace_layout.addWidget(self.investigation_splitter, 1)

        self.activity_workbench_splitter.addWidget(self.command_frame)
        self.activity_workbench_splitter.addWidget(self.inspection_workspace)
        self.activity_workbench_splitter.setStretchFactor(0, 0)
        self.activity_workbench_splitter.setStretchFactor(1, 1)
        self.activity_workbench_splitter.setSizes((220, 340))
        main_layout.addWidget(self.activity_workbench_splitter, 1)
        self.content_splitter.addWidget(self.activity_main)
        self.content_splitter.setStretchFactor(1, 1)
        self._shortcuts = (
            self._make_shortcut("/", self.focus_command_filter),
            self._make_shortcut("Esc", self.clear_filters),
        )
        self._apply_collapse_labels()
        self.render()

    def _make_shortcut(self, sequence: str, callback: Callable[[], None]) -> Any:
        shortcut = QtGui.QShortcut(QtGui.QKeySequence(sequence), self.widget)
        shortcut.setContext(self.QtCore.Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(callback)
        return shortcut

    def refresh(self, sessions: Sequence[WorkspaceSession], records: Sequence[dict[str, Any]]) -> set[ActivityNotification]:
        notices = self.state.refresh(sessions, records)
        self.render()
        return notices

    def reveal_session(self, chat_id: str) -> bool:
        revealed = self.state.reveal_session(chat_id)
        if revealed:
            self.render()
        return revealed

    def render(self) -> None:
        selected_command_id = self._selected_command_id()
        scroll_position = self.command_table.verticalScrollBar().value()
        self.session_model.layoutChanged.emit()
        self.command_model.layoutChanged.emit()
        visible = len(self.state.filtered_sessions())
        self.session_notice.setText(self.state.translator.text("activity.session_notice", visible=visible, total=len(self.state.sessions), closed=len(self.state.closed_session_ids), root=self.state.workspace_root().name))
        selected_name = self.state.session_selected_id or self.state.translator.text("activity.all_workplaces")
        summary = self.state.translator.text(
            "activity.filter_summary",
            workplace=selected_name,
            count=len(self.state.filtered_records()),
        )
        self.filter_summary.setText(summary)
        self.page_subtitle_label.setText(summary)
        self._select_rows(selected_command_id, scroll_position)
        self._restore_command_scroll_after_deferred_layout(scroll_position)

    def _restore_command_scroll_after_deferred_layout(
        self, scroll_position: int
    ) -> None:
        """Keep the user's viewport after QTableView processes model layout events."""
        self._command_scroll_restore_generation += 1
        generation = self._command_scroll_restore_generation

        def restore() -> None:
            if generation != self._command_scroll_restore_generation:
                return
            scroll_bar = self.command_table.verticalScrollBar()
            scroll_bar.setValue(
                max(scroll_bar.minimum(), min(scroll_position, scroll_bar.maximum()))
            )

        self.QtCore.QTimer.singleShot(0, restore)

    def _select_rows(
        self, selected_command_id: str | None, scroll_position: int
    ) -> None:
        sessions = self.state.filtered_sessions()
        selected_session = next((index for index, session in enumerate(sessions) if session.chat_id == self.state.session_selected_id), None)
        if selected_session is not None:
            self.sessions_table.selectRow(selected_session)
        records = self.state.filtered_records()
        selected_command = next(
            (
                index
                for index, record in enumerate(records)
                if self._command_id(record) == selected_command_id
            ),
            None,
        )
        if selected_command is not None:
            self.command_table.selectRow(selected_command)
            self._show_selected_command()
        elif records and selected_command_id is None:
            self.command_table.selectRow(0)
        else:
            self.command_table.clearSelection()
            self.command_table.setCurrentIndex(self.QtCore.QModelIndex())
            self._inspected_command_id = None
            empty = self.state.translator.text("activity.no_commands")
            self._set_editor_text_preserving_scroll(
                self.command_input_view, empty, preserve_scroll=False
            )
            for view in self.inspector_views.values():
                self._set_editor_text_preserving_scroll(
                    view, empty, preserve_scroll=False
                )
        self.command_table.verticalScrollBar().setValue(scroll_position)

    def _set_editor_text_preserving_scroll(
        self, view: Any, text: str, *, preserve_scroll: bool = True
    ) -> None:
        """Update selected command content without losing an editor's viewport."""
        vertical = view.verticalScrollBar()
        horizontal = view.horizontalScrollBar()
        key = id(view)
        if preserve_scroll and view.toPlainText() == text:
            return

        generation = self._editor_scroll_restore_generations.get(key, 0) + 1
        self._editor_scroll_restore_generations[key] = generation

        if preserve_scroll:
            positions = self._editor_pending_scroll_positions.get(
                key, (vertical.value(), horizontal.value())
            )
        else:
            positions = (vertical.minimum(), horizontal.minimum())
            self._editor_pending_scroll_positions.pop(key, None)

        if view.toPlainText() == text:
            vertical.setValue(positions[0])
            horizontal.setValue(positions[1])
            return

        if preserve_scroll:
            self._editor_pending_scroll_positions[key] = positions
        view.setPlainText(text)

        def restore() -> None:
            if self._editor_scroll_restore_generations.get(key) != generation:
                return
            vertical.setValue(
                max(vertical.minimum(), min(positions[0], vertical.maximum()))
            )
            horizontal.setValue(
                max(horizontal.minimum(), min(positions[1], horizontal.maximum()))
            )
            self._editor_pending_scroll_positions.pop(key, None)

        self.QtCore.QTimer.singleShot(0, restore)

    @staticmethod
    def _command_id(record: dict[str, Any]) -> str:
        return str(record.get("operation_id") or record.get("event_id") or "")

    def _selected_command_id(self) -> str | None:
        index = self.command_table.currentIndex()
        records = self.state.filtered_records()
        if index.isValid() and index.row() < len(records):
            selected = self._command_id(records[index.row()])
            if selected:
                self.selected_command_id = selected
        return self.selected_command_id

    def _apply_collapse_labels(self) -> None:
        for collapsed, button, key in (
            (self.input_collapsed, self.input_collapse_button, "action.input"),
            (self.output_collapsed, self.output_collapse_button, "action.output"),
        ):
            label = self.state.translator.text(key)
            action = self.state.translator.text(
                "action.expand" if collapsed else "action.collapse"
            )
            button.setText(f"{'▸' if collapsed else '▾'} {action} {label}")
            button.setAccessibleName(f"{action} {label}")
            button.setToolTip(f"{action} {label}")

    def toggle_input_panel(self) -> None:
        if not self.input_collapsed:
            self._capture_investigation_splitter_sizes()
            self.input_panel.hide()
            self.input_collapsed = True
        else:
            self.input_panel.show()
            self.input_collapsed = False
            self._restore_investigation_splitter_sizes()
        self._apply_collapse_labels()

    def toggle_output_panel(self) -> None:
        if not self.output_collapsed:
            self._capture_investigation_splitter_sizes()
            self.output_panel.hide()
            self.output_collapsed = True
        else:
            self.output_panel.show()
            self.output_collapsed = False
            self._restore_investigation_splitter_sizes()
        self._apply_collapse_labels()

    def _capture_investigation_splitter_sizes(self) -> None:
        if not self.input_collapsed and not self.output_collapsed:
            self._investigation_splitter_sizes = self.vertical_splitter.sizes()

    def _restore_investigation_splitter_sizes(self) -> None:
        if (
            not self.input_collapsed
            and not self.output_collapsed
            and self._investigation_splitter_sizes is not None
        ):
            self.vertical_splitter.setSizes(self._investigation_splitter_sizes)
            self._investigation_splitter_sizes = None

    def _set_workplace_filter(self, value: str) -> None:
        self.state.workplace_filter = value
        self.render()

    def _set_command_filter(self, value: str) -> None:
        self.state.command_filter = value
        self.render()

    def clear_filters(self) -> None:
        self.state.workplace_filter = self.state.command_filter = ""
        self.workplace_filter_input.setText("")
        self.command_filter_input.setText("")
        self.render()

    def show_all_sessions(self) -> None:
        self.state.show_all_sessions()
        self.render()

    def _select_session(self, *_args: Any) -> None:
        index = self.sessions_table.currentIndex()
        sessions = self.state.filtered_sessions()
        if index.isValid() and index.row() < len(sessions):
            self.state.session_selected_id = sessions[index.row()].chat_id
            self.render()

    def _selected_session_id(self) -> str:
        index = self.sessions_table.currentIndex()
        sessions = self.state.filtered_sessions()
        return sessions[index.row()].chat_id if index.isValid() and index.row() < len(sessions) else ""

    def _enable_selected(self) -> None:
        if self.state.enable_session(self._selected_session_id()):
            self.render()

    def _disable_selected(self) -> None:
        if self.state.disable_session(self._selected_session_id()):
            self.render()

    def _close_selected(self) -> None:
        if self.state.close_session(self._selected_session_id()):
            self.render()

    def _sort_records(self, section: int) -> None:
        key = ("time", "workplace", "status", "command", "exit", "duration")[section]
        if key == self.state.sort_key:
            self.state.sort_descending = not self.state.sort_descending
        else:
            self.state.sort_key = key
            self.state.sort_descending = False
        self.render()

    def _show_selected_command(self, *_args: Any) -> None:
        index = self.command_table.currentIndex()
        records = self.state.filtered_records()
        if not index.isValid() or index.row() >= len(records):
            return
        record = records[index.row()]
        command_id = self._command_id(record) or None
        preserve_scroll = command_id == self._inspected_command_id
        self.selected_command_id = command_id
        self._inspected_command_id = command_id
        self._set_editor_text_preserving_scroll(
            self.command_input_view,
            str(record.get("command") or ""),
            preserve_scroll=preserve_scroll,
        )
        for key, content in command_activity_inspector_content(record, self.state.translator).items():
            self._set_editor_text_preserving_scroll(
                self.inspector_views[key], content, preserve_scroll=preserve_scroll
            )

    def copy_active_tab(self) -> None:
        view = self.inspector.widget(self.inspector.currentIndex())
        self.QtWidgets.QApplication.clipboard().setText(view.toPlainText())

    def focus_command_filter(self) -> None:
        self.command_filter_input.setFocus()

    def set_translator(self, translator: DesktopTranslator) -> None:
        self.state.translator = translator
        self.page_title_label.setText(translator.text("nav.gpt_activity"))
        self.session_heading.setText(translator.text("activity.workplaces"))
        self.session_source.setText(translator.text("activity.folder_source"))
        self.workplace_filter_input.setPlaceholderText(translator.text("field.chat_filter"))
        self.command_filter_input.setPlaceholderText(translator.text("activity.command_input"))
        self.clear_button.setText(translator.text("action.clear"))
        self.copy_tab_button.setText(translator.text("action.copy_tab"))
        self._apply_collapse_labels()
        self.command_heading.setText(translator.text("activity.commands"))
        self.input_heading.setText(translator.text("action.input"))
        self.inspector_heading.setText(translator.text("activity.output"))
        for attr, key in (("_all_button", "action.all"), ("_enable_tracking_button", "action.enable_tracking"), ("_disable_tracking_button", "action.disable_tracking"), ("_close_tab_button", "action.close_tab")):
            getattr(self, attr).setText(translator.text(key))
        for index, key in enumerate(("activity.metadata", "activity.stdout", "activity.stderr", "activity.human")):
            self.inspector.setTabText(index, translator.text(key))
        self.session_model.headerDataChanged.emit(self.QtCore.Qt.Horizontal, 0, 2)
        self.command_model.headerDataChanged.emit(self.QtCore.Qt.Horizontal, 0, 5)
        self.render()
