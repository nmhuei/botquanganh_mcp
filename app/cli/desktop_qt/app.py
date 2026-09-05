"""Qt main window and event-loop coordinator for UCS-SecretAgent."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import queue
import threading
import time
from typing import Any

from app.activity_log import read_mcp_command_activity
from app.cli.config_view import set_desktop_ui_language, set_workspace_config
from app.cli.context import CLIContext
from app.cli.desktop_identity import DESKTOP_APP_NAME, DESKTOP_IDENTITY_TEXT
from app.cli.desktop_qt.boot import QtBootSplash
from app.cli.desktop_qt.compat import load_qt_bindings
from app.cli.desktop_qt.theme import COLORS, LAYOUT, build_stylesheet
from app.cli.desktop_qt.widgets import (
    FooterStatusItem,
    HeaderBrand,
    IconRailItem,
    StatusPill,
    load_logo_pixmap,
)
from app.cli.desktop_views.activity import (
    ActivityNotification,
    discover_workspace_sessions,
)
from app.cli.desktop_views.i18n import DesktopTranslator
from app.cli.desktop_views.workspace_logs import make_workspace_log_stream_reader
from app.cli.lifecycle import restart, start, status_data, stop


StatusReader = Callable[[Any, dict[str, str]], dict[str, Any]]
LifecycleAction = Callable[..., dict[str, Any]]
StopConfirmation = Callable[[Any, DesktopTranslator], bool]
ActivityReader = Callable[[int], list[dict[str, Any]]]
WorkspaceLogStreamReader = Callable[[str | None], Any]


NAVIGATION_GLYPHS = {
    "runtime": "⌁",
    "workspace": "▤",
    "gpt": "✦",
}

NAVIGATION_TRANSLATION_KEYS = {
    "runtime": "runtime",
    "workspace": "workspace_logs",
    "gpt": "gpt_activity",
}


def _route_icon(QtCore: Any, QtGui: Any, route: str) -> Any:
    """Draw compact route line art without relying on font glyph availability."""
    pixmap = QtGui.QPixmap(28, 28)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    pen = QtGui.QPen(QtGui.QColor(COLORS["lime"]), 2)
    pen.setCapStyle(QtCore.Qt.RoundCap)
    pen.setJoinStyle(QtCore.Qt.RoundJoin)
    painter.setPen(pen)
    if route == "runtime":
        path = QtGui.QPainterPath()
        path.moveTo(3, 15)
        path.lineTo(8, 15)
        path.lineTo(11, 8)
        path.lineTo(15, 21)
        path.lineTo(19, 12)
        path.lineTo(25, 12)
        painter.drawPath(path)
    elif route == "workspace":
        painter.drawRoundedRect(6, 3, 16, 22, 2, 2)
        for y in (9, 14, 19):
            painter.drawLine(10, y, 18, y)
    else:
        painter.drawEllipse(8, 8, 12, 12)
        painter.drawLine(14, 2, 14, 7)
        painter.drawLine(14, 21, 14, 26)
        painter.drawLine(2, 14, 7, 14)
        painter.drawLine(21, 14, 26, 14)
    painter.end()
    return QtGui.QIcon(pixmap)


def confirm_stop_qt(root: Any, translator: DesktopTranslator) -> bool:
    """Ask for an explicit Qt confirmation, defaulting to the safe answer."""
    from PySide6 import QtWidgets

    answer = QtWidgets.QMessageBox.warning(
        root,
        translator.text("dialog.stop_title"),
        translator.text("dialog.stop_body"),
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        QtWidgets.QMessageBox.No,
    )
    return answer == QtWidgets.QMessageBox.Yes


class QtDesktopDashboard:
    """Compose the reviewed Qt panels and coordinate background work."""

    def __init__(
        self,
        bindings: Any,
        ctx: CLIContext,
        *,
        initial_message: tuple[str, str] | None,
        status_reader: StatusReader,
        start_action: LifecycleAction,
        restart_action: LifecycleAction,
        stop_action: LifecycleAction,
        stop_confirmation: StopConfirmation | None,
        activity_reader: ActivityReader,
        workspace_log_stream_reader: WorkspaceLogStreamReader | None,
    ) -> None:
        from app.cli.desktop_qt.activity import QtActivityPanel
        from app.cli.desktop_qt.runtime import RuntimeCallbacks, RuntimePanel
        from app.cli.desktop_qt.workspace_logs import QtWorkspaceLogsPanel

        self.QtCore = bindings.QtCore
        self.QtGui = bindings.QtGui
        self.QtWidgets = bindings.QtWidgets
        self.ctx = ctx
        self.translator = DesktopTranslator(ctx.values.get("BQA_UI_LANGUAGE", "en"))
        self.status_reader = status_reader
        self.start_action = start_action
        self.restart_action = restart_action
        self.stop_action = stop_action
        self.stop_confirmation = stop_confirmation or confirm_stop_qt
        self.activity_reader = activity_reader
        self.busy = False
        self.refresh_busy = False
        self.closed = False
        self.workspace_selection_dirty = False
        self.latest_status_data: dict[str, Any] | None = None
        self.action_queue: queue.Queue[
            tuple[str, str, Callable[[], None] | None]
        ] = queue.Queue()
        self.refresh_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

        dashboard = self

        class _DashboardWindow(self.QtWidgets.QMainWindow):
            def closeEvent(window_self, event: Any) -> None:
                dashboard._shutdown()
                super().closeEvent(event)

        self.window = _DashboardWindow()
        self.window.setWindowTitle(DESKTOP_APP_NAME)
        self.window.resize(1180, 740)
        self.window.setMinimumSize(980, 680)
        self.window.setStyleSheet(build_stylesheet())
        pixmap = load_logo_pixmap(self.QtGui, 52)
        if pixmap is not None:
            self.window.setWindowIcon(self.QtGui.QIcon(pixmap))

        callbacks = RuntimeCallbacks(
            copy_endpoint=self.copy_endpoint,
            choose_workspace=self.choose_workspace,
            apply_workspace=self.apply_workspace,
            start=self.start_service,
            stop=self.stop_service,
            restart=self.restart_bridge,
            refresh=self.refresh,
        )
        self.runtime_panel = RuntimePanel(
            self.QtCore, self.QtWidgets, self.translator, callbacks
        )
        self.activity_panel = QtActivityPanel(
            self.QtCore,
            self.QtWidgets,
            workspace_root=self.chat_workspaces_root,
            translator=self.translator,
        )
        stream_reader = workspace_log_stream_reader
        if stream_reader is None:
            stream_reader = make_workspace_log_stream_reader(ctx)
        self.workspace_logs_panel = QtWorkspaceLogsPanel(
            self.QtCore,
            self.QtWidgets,
            self.translator,
            on_new_activity=self._on_workspace_activity,
            stream_reader=stream_reader,
            on_message=self._set_message,
            on_status_change=self._set_sse_status,
        )
        self._build()

        self.refresh_timer = self.QtCore.QTimer(self.window)
        self.refresh_timer.setInterval(2_000)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start()
        self.action_drain_timer = self.QtCore.QTimer(self.window)
        self.action_drain_timer.setInterval(50)
        self.action_drain_timer.timeout.connect(self._drain_action_queue)
        self.action_drain_timer.timeout.connect(self._drain_refresh_queue)
        self.action_drain_timer.start()
        self.workspace_logs_panel.start_stream()
        if initial_message:
            self._set_message(*initial_message)
        self.refresh()

    def _build(self) -> None:
        root = self.QtWidgets.QWidget()
        root.setObjectName("appRoot")
        shell = self.QtWidgets.QVBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        self.window.setCentralWidget(root)

        self.command_header = self.QtWidgets.QFrame()
        self.command_header.setObjectName("commandHeader")
        self.command_header.setFixedHeight(LAYOUT["header_height"])
        header = self.QtWidgets.QHBoxLayout(self.command_header)
        header.setContentsMargins(
            LAYOUT["space_lg"], 0, LAYOUT["space_lg"], 0
        )
        header.setSpacing(LAYOUT["space_lg"])
        self.header_brand = HeaderBrand(self.QtWidgets, self.QtGui)
        self.app_name_label = self.header_brand.app_name_label
        self.identity_label = self.header_brand.identity_label
        header.addWidget(self.header_brand.widget)
        self.subtitle_label = self.QtWidgets.QLabel(
            self.translator.text("app.subtitle")
        )
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setProperty("role", "headerSubtitle")
        header.addWidget(self.subtitle_label)
        header.addStretch(1)
        self.status_pill = StatusPill(
            self.QtWidgets, self.translator.text("status.loading")
        )
        header.addWidget(self.status_pill.widget)
        self.language_label = self.QtWidgets.QLabel(
            self.translator.text("label.language")
        )
        header.addWidget(self.language_label)
        self.language_combo = self.QtWidgets.QComboBox()
        self._refresh_language_selector()
        self.language_combo.currentTextChanged.connect(self.change_language)
        header.addWidget(self.language_combo)
        self.close_button = self.QtWidgets.QPushButton(
            self.translator.text("action.close")
        )
        self.close_button.setProperty("role", "compactAction")
        self.close_button.clicked.connect(self.close)
        header.addWidget(self.close_button)
        shell.addWidget(self.command_header)

        self.body_frame = self.QtWidgets.QFrame()
        self.body_frame.setObjectName("commandBody")
        body = self.QtWidgets.QHBoxLayout(self.body_frame)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.icon_rail = self.QtWidgets.QFrame()
        self.icon_rail.setObjectName("iconRail")
        self.icon_rail.setFixedWidth(LAYOUT["rail_width"])
        rail = self.QtWidgets.QVBoxLayout(self.icon_rail)
        rail.setContentsMargins(
            LAYOUT["space_sm"],
            LAYOUT["space_lg"],
            LAYOUT["space_sm"],
            LAYOUT["space_sm"],
        )
        rail.setSpacing(LAYOUT["space_xs"])
        self.content_canvas = self.QtWidgets.QFrame()
        self.content_canvas.setObjectName("contentCanvas")
        content_layout = self.QtWidgets.QVBoxLayout(self.content_canvas)
        content_layout.setContentsMargins(
            20,
            LAYOUT["space_lg"],
            20,
            LAYOUT["space_lg"],
        )
        self.content_stack = self.QtWidgets.QStackedWidget()
        self.stack = self.content_stack
        self.panels = {
            "runtime": self.runtime_panel.widget,
            "workspace": self.workspace_logs_panel.widget,
            "gpt": self.activity_panel.widget,
        }
        self.navigation_items: dict[str, IconRailItem] = {}
        self.navigation_labels: dict[str, Any] = {}
        for route, panel in self.panels.items():
            navigation = IconRailItem(
                self.QtWidgets,
                self.translator.text(
                    f"nav.{NAVIGATION_TRANSLATION_KEYS[route]}"
                ),
                NAVIGATION_GLYPHS[route],
                lambda _checked=False, route=route: self._show_page(route),
            )
            navigation.set_active(route == "runtime")
            navigation.button.setText("")
            navigation.button.setIcon(_route_icon(self.QtCore, self.QtGui, route))
            navigation.button.setIconSize(self.QtCore.QSize(26, 26))
            navigation.button.setFixedHeight(42)
            navigation.button.setSizePolicy(
                self.QtWidgets.QSizePolicy.Expanding,
                self.QtWidgets.QSizePolicy.Fixed,
            )
            self.navigation_items[route] = navigation
            label = self.QtWidgets.QLabel(
                self.translator.text(f"nav.{NAVIGATION_TRANSLATION_KEYS[route]}")
            )
            label.setAlignment(self.QtCore.Qt.AlignHCenter)
            label.setWordWrap(True)
            label.setProperty("role", "railLabel")
            self.navigation_labels[route] = label
            rail.addWidget(navigation.button)
            rail.addWidget(label)
            self.content_stack.addWidget(panel)
        self.navigation_buttons = self.navigation_items
        rail.addStretch(1)
        content_layout.addWidget(self.content_stack)
        body.addWidget(self.icon_rail)
        body.addWidget(self.content_canvas, 1)
        shell.addWidget(self.body_frame, 1)

        self.footer_bar = self.QtWidgets.QFrame()
        self.footer_bar.setObjectName("footerBar")
        self.footer_bar.setFixedHeight(36)
        footer = self.QtWidgets.QHBoxLayout(self.footer_bar)
        footer.setContentsMargins(LAYOUT["space_lg"], 0, LAYOUT["space_lg"], 0)
        footer.setSpacing(LAYOUT["space_md"])
        self.backend_label = FooterStatusItem(self.QtWidgets, "backend: —").widget
        self.workspace_label = FooterStatusItem(
            self.QtWidgets, str(self.ctx.values.get("HOST_WORKSPACE_DIR", ""))
        ).widget
        self.refresh_label = FooterStatusItem(self.QtWidgets, "refresh: —").widget
        self.sse_label = FooterStatusItem(self.QtWidgets, "SSE: CONNECTING").widget
        self.message_label = self.QtWidgets.QLabel("")
        self.message_label.setWordWrap(True)
        footer_labels = (
            self.backend_label,
            self.workspace_label,
            self.refresh_label,
            self.sse_label,
        )
        for index, label in enumerate(footer_labels):
            footer.addWidget(label)
            if index < len(footer_labels) - 1:
                separator = self.QtWidgets.QFrame()
                separator.setObjectName("footerSeparator")
                separator.setFrameShape(self.QtWidgets.QFrame.VLine)
                footer.addWidget(separator)
        footer.addWidget(self.message_label, 1)
        shell.addWidget(self.footer_bar)

    def select_view(self, index: int) -> None:
        routes = tuple(self.navigation_items)
        if 0 <= index < len(routes):
            self._show_page(routes[index])

    def _show_page(self, route: str) -> None:
        index = tuple(self.navigation_items).index(route)
        self.content_stack.setCurrentIndex(index)
        for item_route, navigation in self.navigation_items.items():
            navigation.set_active(item_route == route)

    def _language_options(self) -> dict[str, str]:
        return {
            self.translator.text("language.en"): "en",
            self.translator.text("language.vi"): "vi",
        }

    def _refresh_language_selector(self) -> None:
        self.language_choices = self._language_options()
        selected = next(
            label
            for label, language in self.language_choices.items()
            if language == self.translator.language
        )
        self.language_combo.blockSignals(True)
        self.language_combo.clear()
        self.language_combo.addItems(tuple(self.language_choices))
        self.language_combo.setCurrentText(selected)
        self.language_combo.blockSignals(False)

    def change_language(self, selection: str) -> None:
        language = self.language_choices.get(selection)
        if language is None or language == self.translator.language:
            return
        try:
            updated = set_desktop_ui_language(self.ctx.repo_root, language)
        except ValueError as exc:
            self._refresh_language_selector()
            self._set_message(
                "error", self.translator.text("message.language_error", error=str(exc))
            )
            return
        self.ctx.values.update(updated)
        self.translator = DesktopTranslator(updated["BQA_UI_LANGUAGE"])
        self.subtitle_label.setText(self.translator.text("app.subtitle"))
        self.language_label.setText(self.translator.text("label.language"))
        self.close_button.setText(self.translator.text("action.close"))
        for route, navigation in self.navigation_items.items():
            label = self.translator.text(
                f"nav.{NAVIGATION_TRANSLATION_KEYS[route]}"
            )
            navigation.button.setAccessibleName(label)
            navigation.button.setToolTip(label)
            self.navigation_labels[route].setText(label)
        pending_workspace = (
            self.runtime_panel.workspace_value.text()
            if self.workspace_selection_dirty
            else None
        )
        self.runtime_panel.set_translator(
            self.translator, pending_workspace=pending_workspace
        )
        self.workspace_logs_panel.set_translator(self.translator)
        self.activity_panel.set_translator(self.translator)
        self._refresh_language_selector()
        self._set_message(
            "success",
            self.translator.text(
                "message.language_saved",
                language=self.translator.text(f"language.{self.translator.language}"),
            ),
        )

    def chat_workspaces_root(self) -> Path:
        configured = self.ctx.values.get("HOST_CHAT_ROOT", "").strip()
        if configured:
            return Path(configured).expanduser()
        return Path.home() / "Downloads" / "bqa-workspaces"

    def _on_workspace_activity(self, notification: ActivityNotification) -> None:
        self.activity_panel.reveal_session(notification.chat_id)

    def _set_sse_status(self, state: str) -> None:
        self.sse_label.setText(f"SSE: {state.upper()}")

    def _set_message(self, kind: str, text: str) -> None:
        color = {
            "success": COLORS["success"],
            "warn": COLORS["warning"],
            "error": COLORS["danger"],
        }.get(kind, COLORS["muted"])
        self.message_label.setText(text)
        self.message_label.setStyleSheet(f"color: {color};")

    def refresh(self) -> None:
        """Read status and activity off-thread; the drain timer renders results."""
        if self.closed or self.refresh_busy:
            return
        self.refresh_busy = True

        def worker() -> None:
            try:
                data = self.status_reader(self.ctx.repo_root, self.ctx.values)
                self.refresh_queue.put(("status", ("ok", data)))
            except Exception as exc:
                self.refresh_queue.put(("status", ("error", str(exc))))
            try:
                records = self.activity_reader(100)
                sessions = discover_workspace_sessions(self.chat_workspaces_root())
                self.refresh_queue.put(("activity", ("ok", sessions, records)))
            except Exception as exc:
                self.refresh_queue.put(("activity", ("error", str(exc))))
            self.refresh_queue.put(("complete", time.strftime("%H:%M:%S")))

        threading.Thread(
            target=worker, name="bqa-qt-desktop-refresh", daemon=True
        ).start()

    def _drain_refresh_queue(self) -> None:
        while not self.closed:
            try:
                kind, payload = self.refresh_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                outcome, value = payload
                if outcome == "ok":
                    self._render_status(value)
                else:
                    self.status_pill.set_state(
                        self.translator.text("status.needs_attention"), "error"
                    )
                    self._set_message(
                        "error",
                        self.translator.text("message.status_error", error=value),
                    )
            elif kind == "activity":
                outcome, *values = payload
                if outcome == "ok":
                    sessions, records = values
                    for notification in self.activity_panel.refresh(sessions, records):
                        self._on_workspace_activity(notification)
                else:
                    self._set_message(
                        "error",
                        self.translator.text("message.activity_error", error=values[0]),
                    )
            elif kind == "complete":
                self.refresh_busy = False
                self.refresh_label.setText(f"refresh: {payload}")

    def _render_status(self, data: dict[str, Any]) -> None:
        runtime_data = dict(data)
        if self.workspace_selection_dirty:
            runtime_data["workspace"] = self.runtime_panel.workspace_value.text()
        presentation = self.runtime_panel.render(runtime_data)
        self.latest_status_data = dict(data)
        state = "success" if data.get("ok") else "warn"
        self.status_pill.set_state(presentation.status, state)
        running = bool((data.get("server") or {}).get("running"))
        self.backend_label.setText(
            self.translator.text("backend.alive" if running else "backend.down")
        )
        if not self.workspace_selection_dirty:
            workspace = str(
                data.get("workspace")
                or self.ctx.values.get("HOST_WORKSPACE_DIR", "")
            )
            self.runtime_panel.workspace_value.setText(workspace)
            self.workspace_label.setText(workspace)
        if not self.busy:
            self._set_message(
                "success" if data.get("ok") else "warn", presentation.summary
            )

    def _run_action(
        self,
        label: str,
        action: Callable[[], dict[str, Any]],
        *,
        on_success: Callable[[], None] | None = None,
    ) -> None:
        if self.busy or self.closed:
            return
        self.busy = True
        self.runtime_panel.set_busy(True)
        self._set_message(
            "warn", self.translator.text("message.running_action", action=label)
        )

        def worker() -> None:
            try:
                result = action()
                kind = "success" if result.get("ok", True) else "error"
                fallback_key = (
                    "message.action_complete"
                    if result.get("ok", True)
                    else "message.action_failed"
                )
                text = str(
                    result.get("message")
                    or self.translator.text(fallback_key, action=label)
                )
            except Exception as exc:
                kind = "error"
                text = self.translator.text(
                    "message.action_error", action=label.lower(), error=str(exc)
                )
            completion = on_success if kind == "success" else None
            self.action_queue.put((kind, text, completion))

        threading.Thread(
            target=worker, name="bqa-qt-desktop-action", daemon=True
        ).start()

    def _drain_action_queue(self) -> None:
        while not self.closed:
            try:
                kind, text, on_success = self.action_queue.get_nowait()
            except queue.Empty:
                break
            self.busy = False
            self.runtime_panel.set_busy(False)
            if on_success is not None:
                on_success()
            self._set_message(kind, text)
            self.refresh()

    def start_service(self) -> None:
        self._run_action(
            self.translator.text("action.start_adopt"),
            lambda: self.start_action(self.ctx.repo_root),
        )

    def stop_service(self) -> None:
        if self.busy or self.closed:
            return
        if not self.stop_confirmation(self.window, self.translator):
            return
        self._run_action(
            self.translator.text("action.stop"),
            lambda: self.stop_action(self.ctx.repo_root),
        )

    def restart_bridge(self) -> None:
        self._run_action(
            self.translator.text("action.restart_bridge"),
            lambda: self.restart_action(self.ctx.repo_root, self.ctx.values),
        )

    def choose_workspace(self) -> None:
        if self.busy or self.closed:
            return
        selected = self.QtWidgets.QFileDialog.getExistingDirectory(
            self.window,
            self.translator.text("dialog.choose_workspace"),
            self.runtime_panel.workspace_value.text(),
        )
        if selected:
            self.runtime_panel.workspace_value.setText(selected)
            self.workspace_selection_dirty = True
            self._set_message(
                "warn", self.translator.text("message.workspace_selected")
            )

    def apply_workspace(self) -> None:
        if self.busy or self.closed:
            return
        selected = self.runtime_panel.workspace_value.text()

        def apply() -> dict[str, Any]:
            self.ctx.values.update(set_workspace_config(self.ctx.repo_root, selected))
            result = self.restart_action(self.ctx.repo_root, self.ctx.values)
            return {
                "ok": bool(result.get("ok", True)),
                "message": self.translator.text("message.workspace_saved"),
            }

        self._run_action(
            self.translator.text("action.apply"),
            apply,
            on_success=lambda: self._workspace_apply_succeeded(selected),
        )

    def _workspace_apply_succeeded(self, selected: str) -> None:
        self.workspace_selection_dirty = False
        self.workspace_label.setText(selected)

    def copy_endpoint(self) -> None:
        endpoint = ""
        if self.latest_status_data is not None:
            endpoint = str(
                self.latest_status_data.get("url")
                or self.latest_status_data.get("last_known_url")
                or ""
            )
        if not endpoint:
            self._set_message("warn", self.translator.text("message.no_endpoint"))
            return
        self.QtWidgets.QApplication.clipboard().setText(endpoint)
        self._set_message("success", self.translator.text("message.endpoint_copied"))

    def _shutdown(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.refresh_timer.stop()
        self.action_drain_timer.stop()
        self.workspace_logs_panel.close()

    def close(self) -> None:
        self._shutdown()
        self.window.close()


def run_qt_desktop_ui(
    ctx: CLIContext,
    *,
    initial_message: tuple[str, str] | None = None,
    status_reader: StatusReader = status_data,
    start_action: LifecycleAction = start,
    restart_action: LifecycleAction = restart,
    stop_action: LifecycleAction = stop,
    stop_confirmation: StopConfirmation | None = None,
    activity_reader: ActivityReader = read_mcp_command_activity,
    workspace_log_stream_reader: WorkspaceLogStreamReader | None = None,
) -> int:
    """Launch the PySide desktop window without blocking its UI thread."""
    bindings = load_qt_bindings()
    application = bindings.QtWidgets.QApplication.instance()
    if application is None:
        application = bindings.QtWidgets.QApplication([])
    application.setApplicationName(DESKTOP_APP_NAME)
    application.setStyleSheet(build_stylesheet())
    dashboard = QtDesktopDashboard(
        bindings,
        ctx,
        initial_message=initial_message,
        status_reader=status_reader,
        start_action=start_action,
        restart_action=restart_action,
        stop_action=stop_action,
        stop_confirmation=stop_confirmation,
        activity_reader=activity_reader,
        workspace_log_stream_reader=workspace_log_stream_reader,
    )
    splash = QtBootSplash(
        bindings.QtCore,
        bindings.QtGui,
        bindings.QtWidgets,
        on_ready=dashboard.window.show,
    )
    application.aboutToQuit.connect(dashboard._shutdown)
    splash.start()
    try:
        return int(application.exec())
    finally:
        dashboard._shutdown()
