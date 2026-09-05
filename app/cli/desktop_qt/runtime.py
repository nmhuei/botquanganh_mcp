"""PySide runtime panel driven only by the desktop presentation layer."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.cli.desktop_qt.theme import COLORS
from app.cli.desktop_qt.widgets import (
    DetailRow,
    MetricCell,
    SectionHeading,
    ServiceDetailCard,
    StatusPill,
    apply_button_variant,
)
from app.cli.desktop_views.i18n import DesktopTranslator
from app.cli.desktop_views.runtime import RuntimePresentation, runtime_presentation


def _service_icon_pixmap(QtCore: Any, QtGui: Any, index: int) -> Any:
    """Draw one compact service mark using the shared UCS accent."""
    pixmap = QtGui.QPixmap(32, 32)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setPen(QtGui.QPen(QtGui.QColor(COLORS["lime"]), 2))
    if index == 0:
        painter.drawEllipse(5, 5, 22, 22)
        painter.drawLine(10, 16, 22, 16)
        painter.drawLine(16, 10, 16, 22)
    elif index == 1:
        painter.drawRoundedRect(6, 5, 20, 8, 2, 2)
        painter.drawRoundedRect(6, 19, 20, 8, 2, 2)
        painter.drawPoint(10, 9)
        painter.drawPoint(10, 23)
    else:
        painter.drawArc(5, 10, 22, 16, 20 * 16, 140 * 16)
        painter.drawArc(5, 10, 22, 16, 200 * 16, 140 * 16)
        painter.drawLine(9, 21, 23, 21)
    painter.end()
    return pixmap


@dataclass(frozen=True)
class RuntimeCallbacks:
    copy_endpoint: Callable[[], None]
    choose_workspace: Callable[[], None]
    apply_workspace: Callable[[], None]
    start: Callable[[], None]
    stop: Callable[[], None]
    restart: Callable[[], None]
    refresh: Callable[[], None]


class RuntimePanel:
    """Render normalized runtime state and forward UI events to callbacks."""

    def __init__(
        self,
        QtCore: Any,
        QtWidgets: Any,
        translator: DesktopTranslator,
        callbacks: RuntimeCallbacks,
    ) -> None:
        self.QtCore = QtCore
        self.QtWidgets = QtWidgets
        self.translator = translator
        self.callbacks = callbacks
        self.latest_data: dict[str, Any] | None = None
        self.widget = QtWidgets.QWidget()
        self.widget.setObjectName("runtimePage")
        self.page_heading = SectionHeading(
            QtWidgets,
            translator.text("nav.runtime"),
        )
        self.page_heading.widget.setObjectName("pageHeader")
        self.page_title_label = self.page_heading.title_label
        self.page_title_label.setProperty("role", "pageTitle")
        self.page_subtitle_label = QtWidgets.QLabel(
            translator.text("runtime.overview")
        )
        self.page_subtitle_label.setProperty("role", "pageSubtitle")
        self.page_heading.widget.layout().addWidget(self.page_subtitle_label)
        self.status_pill = StatusPill(QtWidgets, translator.text("status.loading"))
        self.status_label = self.status_pill.widget
        self.summary_label = QtWidgets.QLabel("")
        self.endpoint_value = QtWidgets.QLabel(translator.text("status.not_available"))
        self.workspace_value = QtWidgets.QLineEdit("")
        self.workspace_value.setReadOnly(True)
        self.bridge_value = QtWidgets.QLabel(translator.text("status.not_available"))
        self.server_value = QtWidgets.QLabel(translator.text("status.not_available"))
        self.tunnel_value = QtWidgets.QLabel(translator.text("status.not_available"))
        self.start_button = QtWidgets.QPushButton(translator.text("action.start"))
        self.stop_button = QtWidgets.QPushButton(translator.text("action.stop"))
        self.restart_button = QtWidgets.QPushButton(translator.text("action.restart"))
        self.refresh_button = QtWidgets.QPushButton(translator.text("action.refresh"))
        self.action_buttons = [
            self.start_button,
            self.stop_button,
            self.restart_button,
            self.refresh_button,
        ]
        self._build()

    def _build(self) -> None:
        from PySide6 import QtGui

        layout = self.QtWidgets.QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.page_heading.widget)

        self.metric_strip = self.QtWidgets.QFrame()
        self.metric_strip.setObjectName("runtimeMetricStrip")
        self.metric_strip.setProperty("role", "card")
        self.metric_strip.setMinimumHeight(96)
        metric_layout = self.QtWidgets.QHBoxLayout(self.metric_strip)
        metric_layout.setContentsMargins(12, 10, 12, 10)
        metric_layout.setSpacing(8)
        self.metric_cells: list[MetricCell] = []

        status_metric = MetricCell(
            self.QtWidgets,
            self.translator.text("field.runtime_status"),
            self.translator.text("status.loading"),
        )
        status_metric.layout.replaceWidget(status_metric.value, self.status_label)
        self.metric_cells.append(status_metric)

        endpoint_metric = MetricCell(
            self.QtWidgets,
            self.translator.text("field.endpoint"),
            self.translator.text("status.not_available"),
        )
        endpoint_metric.layout.replaceWidget(endpoint_metric.value, self.endpoint_value)
        self.endpoint_value.setWordWrap(False)
        self.endpoint_value.setTextInteractionFlags(self.QtCore.Qt.TextSelectableByMouse)
        self.copy_button = self.QtWidgets.QPushButton(self.translator.text("action.copy"))
        self.copy_button.setObjectName("runtimeCopyEndpointButton")
        self.copy_button.clicked.connect(self.callbacks.copy_endpoint)
        apply_button_variant(self.copy_button, "secondary")
        endpoint_metric.layout.addWidget(self.copy_button)
        self.metric_cells.append(endpoint_metric)

        signal_metric = MetricCell(
            self.QtWidgets,
            self.translator.text("runtime.status_summary"),
            self.translator.text("status.not_available"),
        )
        signal_metric.layout.replaceWidget(signal_metric.value, self.summary_label)
        self.summary_label.setWordWrap(True)
        self.metric_cells.append(signal_metric)

        for metric in self.metric_cells:
            metric.widget.setSizePolicy(
                self.QtWidgets.QSizePolicy.Expanding,
                self.QtWidgets.QSizePolicy.Preferred,
            )
            metric_layout.addWidget(metric.widget, 1)
        # Keep this alias for callers that previously only needed the overview frame.
        self.health_strip = self.metric_strip
        layout.addWidget(self.metric_strip)

        self.service_grid = self.QtWidgets.QGridLayout()
        self.service_grid.setHorizontalSpacing(12)
        self.service_grid.setVerticalSpacing(12)
        self.service_cards: list[ServiceDetailCard] = []
        self.service_icon_labels: list[Any] = []
        self.service_pills: list[StatusPill] = []
        self._service_card_keys: list[str] = []
        self._service_detail_rows: list[list[DetailRow]] = []
        self._service_detail_values: list[list[Any]] = []
        self._detail_row_label_keys: list[list[str]] = []
        for title_key, value, detail_keys in (
            (
                "field.mcp_bridge",
                self.bridge_value,
                ("field.runtime_status", "field.authentication", "field.endpoint"),
            ),
            (
                "field.server",
                self.server_value,
                ("field.runtime_status", "field.endpoint", "runtime.status_summary"),
            ),
            (
                "field.tunnel",
                self.tunnel_value,
                ("field.runtime_status", "field.endpoint", "runtime.status_summary"),
            ),
        ):
            card = ServiceDetailCard(self.QtWidgets, self.translator.text(title_key))
            card.widget.setSizePolicy(
                self.QtWidgets.QSizePolicy.Expanding,
                self.QtWidgets.QSizePolicy.Preferred,
            )
            card.layout.removeWidget(card.title)
            header = self.QtWidgets.QHBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            icon_label = self.QtWidgets.QLabel()
            icon_label.setPixmap(
                _service_icon_pixmap(self.QtCore, QtGui, len(self.service_cards))
            )
            icon_label.setFixedSize(32, 32)
            header.addWidget(icon_label)
            header.addWidget(card.title)
            header.addStretch(1)
            pill = StatusPill(self.QtWidgets)
            header.addWidget(pill.widget)
            card.layout.addLayout(header)

            rows: list[DetailRow] = []
            values: list[Any] = []
            for row_index, detail_key in enumerate(detail_keys):
                row = DetailRow(
                    self.QtWidgets,
                    self.translator.text(detail_key),
                    self.translator.text("status.not_available"),
                )
                if row_index == 0:
                    row.layout.replaceWidget(row.value, value)
                    value.setProperty("role", "detailValue")
                    value.setWordWrap(False)
                    row_value = value
                else:
                    row_value = row.value
                    row_value.setWordWrap(detail_key == "runtime.status_summary")
                card.layout.addWidget(row.widget)
                rows.append(row)
                values.append(row_value)
            card.detail_rows = rows
            card.detail_row_count = len(rows)
            self.service_cards.append(card)
            self.service_icon_labels.append(icon_label)
            self.service_pills.append(pill)
            self._service_card_keys.append(title_key)
            self._service_detail_rows.append(rows)
            self._service_detail_values.append(values)
            self._detail_row_label_keys.append(list(detail_keys))
            column = len(self.service_cards) - 1
            self.service_grid.addWidget(card.widget, 0, column)
            self.service_grid.setColumnStretch(column, 1)
        layout.addLayout(self.service_grid)

        self.workspace_frame = self.QtWidgets.QFrame()
        self.workspace_frame.setObjectName("runtimeWorkspaceFrame")
        self.workspace_frame.setProperty("role", "card")
        workspace_row = self.QtWidgets.QHBoxLayout(self.workspace_frame)
        workspace_row.setContentsMargins(12, 10, 12, 10)
        workspace_row.setSpacing(8)
        self.workspace_label = self.QtWidgets.QLabel(
            self.translator.text("field.workspace")
        )
        self.workspace_label.setProperty("role", "cardTitle")
        workspace_row.addWidget(self.workspace_label)
        workspace_row.addWidget(self.workspace_value, 1)
        self.choose_button = self.QtWidgets.QPushButton(
            self.translator.text("action.choose_folder")
        )
        self.choose_button.setObjectName("runtimeChooseWorkspaceButton")
        self.choose_button.clicked.connect(self.callbacks.choose_workspace)
        self.apply_button = self.QtWidgets.QPushButton(self.translator.text("action.apply"))
        self.apply_button.setObjectName("runtimeApplyWorkspaceButton")
        self.apply_button.clicked.connect(self.callbacks.apply_workspace)
        apply_button_variant(self.choose_button, "secondary")
        apply_button_variant(self.apply_button, "primary")
        self.workspace_buttons = [self.choose_button, self.apply_button]
        workspace_row.addWidget(self.choose_button)
        workspace_row.addWidget(self.apply_button)
        layout.addWidget(self.workspace_frame)

        self.action_dock = self.QtWidgets.QFrame()
        self.action_dock.setObjectName("runtimeActionDock")
        self.action_dock.setProperty("role", "card")
        action_row = self.QtWidgets.QHBoxLayout(self.action_dock)
        action_row.setContentsMargins(12, 10, 12, 10)
        self.action_dock_label = self.QtWidgets.QLabel(
            self.translator.text("runtime.controls")
        )
        self.action_dock_label.setProperty("role", "cardTitle")
        action_row.addWidget(self.action_dock_label)
        for button, callback, variant in (
            (self.start_button, self.callbacks.start, "primary"),
            (self.refresh_button, self.callbacks.refresh, "secondary"),
            (self.restart_button, self.callbacks.restart, "secondary"),
        ):
            button.clicked.connect(callback)
            apply_button_variant(button, variant)
            button.setSizePolicy(
                self.QtWidgets.QSizePolicy.Expanding,
                self.QtWidgets.QSizePolicy.Preferred,
            )
            action_row.addWidget(button, 1)
        self.stop_button.setObjectName("runtimeStopButton")
        self.stop_button.clicked.connect(self.callbacks.stop)
        apply_button_variant(self.stop_button, "danger")
        self.stop_button.setSizePolicy(
            self.QtWidgets.QSizePolicy.Expanding,
            self.QtWidgets.QSizePolicy.Preferred,
        )
        action_row.addSpacing(8)
        action_row.addWidget(self.stop_button, 1)
        self.start_button.setObjectName("runtimeStartButton")
        self.refresh_button.setObjectName("runtimeRefreshButton")
        self.restart_button.setObjectName("runtimeRestartButton")
        layout.addWidget(self.action_dock)
        layout.addStretch(1)

    def render(self, data: dict[str, Any]) -> RuntimePresentation:
        self.latest_data = dict(data)
        presentation = runtime_presentation(data, self.translator)
        self.status_label.setText(presentation.status)
        self.summary_label.setText(presentation.summary)
        self.bridge_value.setText(presentation.bridge)
        self.server_value.setText(presentation.server)
        self.tunnel_value.setText(presentation.tunnel)
        self.endpoint_value.setText(presentation.endpoint)
        self.workspace_value.setText(str(data.get("workspace") or ""))
        self.status_pill.set_state(
            presentation.status, self._health_visual_state(presentation)
        )
        for pill, value in zip(
            self.service_pills,
            (presentation.bridge, presentation.server, presentation.tunnel),
            strict=True,
        ):
            pill.set_state(value, self._service_visual_state(value))
        for detail_values, values in zip(
            self._service_detail_values,
            (
                (presentation.bridge, presentation.authentication, presentation.endpoint),
                (presentation.server, presentation.endpoint, presentation.summary),
                (presentation.tunnel, presentation.endpoint, presentation.summary),
            ),
            strict=True,
        ):
            for label, text in zip(detail_values, values, strict=True):
                label.setText(text)
        return presentation

    def _health_visual_state(self, presentation: RuntimePresentation) -> str:
        """Map an existing normalized health result to a stable pill selector."""
        return {
            self.translator.text("status.ready"): "ready",
            self.translator.text("status.needs_attention"): "warning",
            self.translator.text("status.stopped"): "stopped",
        }.get(presentation.status, "warning")

    def _service_visual_state(self, value: str) -> str:
        """Map an existing service display value without deriving lifecycle data."""
        normalized = value.casefold()
        if normalized in {
            "ready",
            self.translator.text("status.running").casefold(),
        }:
            return "ready"
        if normalized in {
            "stopped",
            self.translator.text("status.stopped_value").casefold(),
        }:
            return "stopped"
        return "warning"

    def set_busy(self, busy: bool) -> None:
        for button in (*self.action_buttons, *self.workspace_buttons):
            button.setEnabled(not busy)

    def set_translator(
        self, translator: DesktopTranslator, *, pending_workspace: str | None = None
    ) -> None:
        self.translator = translator
        self.start_button.setText(translator.text("action.start"))
        self.stop_button.setText(translator.text("action.stop"))
        self.restart_button.setText(translator.text("action.restart"))
        self.refresh_button.setText(translator.text("action.refresh"))
        self.copy_button.setText(translator.text("action.copy"))
        self.choose_button.setText(translator.text("action.choose_folder"))
        self.apply_button.setText(translator.text("action.apply"))
        self.page_title_label.setText(translator.text("nav.runtime"))
        self.page_subtitle_label.setText(translator.text("runtime.overview"))
        self.workspace_label.setText(translator.text("field.workspace"))
        self.action_dock_label.setText(translator.text("runtime.controls"))
        for metric, label_key in zip(
            self.metric_cells,
            ("field.runtime_status", "field.endpoint", "runtime.status_summary"),
            strict=True,
        ):
            metric.label.setText(translator.text(label_key))
        for title_key, card in zip(self._service_card_keys, self.service_cards, strict=True):
            card.title.setText(translator.text(title_key))
        for rows, label_keys in zip(
            self._service_detail_rows, self._detail_row_label_keys, strict=True
        ):
            for row, label_key in zip(rows, label_keys, strict=True):
                row.label.setText(translator.text(label_key))
        if self.latest_data is not None:
            self.render(self.latest_data)
            if pending_workspace is not None:
                self.workspace_value.setText(pending_workspace)
        else:
            self.status_label.setText(translator.text("status.loading"))
            self.summary_label.setText(translator.text("status.not_available"))
            self.endpoint_value.setText(translator.text("status.not_available"))
            self.bridge_value.setText(translator.text("status.not_available"))
            self.server_value.setText(translator.text("status.not_available"))
            self.tunnel_value.setText(translator.text("status.not_available"))
            for detail_values in self._service_detail_values:
                for value in detail_values[1:]:
                    value.setText(translator.text("status.not_available"))
