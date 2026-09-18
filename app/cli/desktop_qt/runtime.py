"""PySide runtime panel driven only by the desktop presentation layer."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math
import time
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

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


def _service_icon_pixmap(QtCore: Any, QtGui: Any, index: int, color: str | None = None) -> Any:
    """Draw one crisp, balanced service mark using the shared UCS accent without clipping."""
    size = 24
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setPen(QtGui.QPen(QtGui.QColor(color or COLORS["lime"]), 1.8))
    if index == 0:
        # Bridge / Hub icon: centered globe / node network
        painter.drawEllipse(3, 3, 18, 18)
        painter.drawLine(6, 12, 18, 12)
        painter.drawLine(12, 6, 12, 18)
    elif index == 1:
        # Server icon: dual rack units
        painter.drawRoundedRect(3, 4, 18, 6, 1.5, 1.5)
        painter.drawRoundedRect(3, 13, 18, 6, 1.5, 1.5)
        painter.drawPoint(6, 7)
        painter.drawPoint(6, 16)
    else:
        # Tunnel icon: nested signal arcs
        painter.drawArc(3, 5, 18, 14, 25 * 16, 130 * 16)
        painter.drawArc(6, 8, 12, 10, 25 * 16, 130 * 16)
        painter.drawLine(4, 18, 20, 18)
    painter.end()
    return pixmap


class McpVirtualSpectrumBar(QtWidgets.QWidget):
    """Futuristic virtual diagram bar showing real-time MCP pipeline and animated activity spectrum."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(54)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self.is_online = False
        self.health_pct = 0
        self.accent_color = COLORS["lime"]
        self.subsystems = {
            "GW": False,
            "SERVER": False,
            "BRIDGE": False,
            "TOOLS": False,
        }
        self._phase = 0.0

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(40)  # 25 FPS
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    def _on_tick(self) -> None:
        if self.is_online:
            self._phase += 0.12
            self.update()

    def set_state(self, data: dict[str, Any], accent: str | None = None) -> None:
        if accent:
            self.accent_color = accent
        srv_running = bool((data.get("server") or {}).get("running"))
        tun_running = bool((data.get("tunnel") or {}).get("running"))
        brg_ready = str(data.get("bridge") or "").lower() in {"ready", "running", "ok"}
        ws_ready = bool(data.get("workspace"))

        self.subsystems = {
            "GW": tun_running,
            "SERVER": srv_running,
            "BRIDGE": brg_ready,
            "TOOLS": ws_ready or srv_running,
        }

        active_count = sum(1 for v in self.subsystems.values() if v)
        self.health_pct = int((active_count / max(1, len(self.subsystems))) * 100)
        self.is_online = active_count > 0
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        w = self.width()
        h = self.height()

        # Frame background
        bg_rect = QtCore.QRectF(0, 0, w, h)
        painter.setBrush(QtGui.QBrush(QtGui.QColor(10, 16, 15, 200)))
        painter.setPen(QtGui.QPen(QtGui.QColor(42, 54, 50), 1.0))
        painter.drawRoundedRect(bg_rect, 6.0, 6.0)

        # 1. Top Section: 4 Pipeline Segment Nodes [GW] ─ [SRV] ─ [BRG] ─ [TOOLS]
        node_names = [("GW", "GATEWAY"), ("SRV", "SERVER"), ("BRG", "BRIDGE"), ("TOOLS", "TOOLS")]
        node_w = 42
        node_h = 15
        node_y = 6
        gap = 8
        start_x = 8

        font_node = QtGui.QFont("Monospace", 7, QtGui.QFont.Bold)
        font_node.setStyleHint(QtGui.QFont.Monospace)
        painter.setFont(font_node)

        accent_qcolor = QtGui.QColor(self.accent_color)
        dim_qcolor = QtGui.QColor(129, 144, 138, 80)

        for i, (short_name, full_name) in enumerate(node_names):
            active = self.subsystems.get(short_name, False) or self.subsystems.get(full_name, False)
            nx = start_x + i * (node_w + gap)
            nrect = QtCore.QRectF(nx, node_y, node_w, node_h)

            if active:
                painter.setBrush(QtGui.QBrush(QtGui.QColor(accent_qcolor.red(), accent_qcolor.green(), accent_qcolor.blue(), 35)))
                painter.setPen(QtGui.QPen(accent_qcolor, 1.0))
                painter.drawRoundedRect(nrect, 3.0, 3.0)
                painter.setPen(accent_qcolor)
                painter.drawText(nrect, QtCore.Qt.AlignCenter, short_name)
            else:
                painter.setBrush(QtGui.QBrush(QtGui.QColor(20, 20, 20, 100)))
                painter.setPen(QtGui.QPen(dim_qcolor, 0.8))
                painter.drawRoundedRect(nrect, 3.0, 3.0)
                painter.setPen(dim_qcolor)
                painter.drawText(nrect, QtCore.Qt.AlignCenter, short_name)

            # Connector line to next node
            if i < len(node_names) - 1:
                cx = nx + node_w + 1
                cy = node_y + node_h / 2
                painter.setPen(QtGui.QPen(accent_qcolor if active else dim_qcolor, 1.2))
                painter.drawLine(QtCore.QPointF(cx, cy), QtCore.QPointF(cx + gap - 2, cy))

        # Health percentage badge on top right
        font_pct = QtGui.QFont("Monospace", 8, QtGui.QFont.Black)
        font_pct.setStyleHint(QtGui.QFont.Monospace)
        painter.setFont(font_pct)
        if self.is_online and self.health_pct == 100:
            pct_color = accent_qcolor
            pct_text = "● 100%"
        elif self.is_online:
            pct_color = QtGui.QColor("#f4b942")
            pct_text = f"▲ {self.health_pct}%"
        else:
            pct_color = QtGui.QColor("#ff6b61")
            pct_text = "○ OFF"

        painter.setPen(pct_color)
        painter.drawText(QtCore.QRectF(w - 70, node_y, 62, node_h), QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, pct_text)

        # 2. Bottom Section: 24 Animated Virtual Spectrum / Activity Bars
        spec_y = 28
        spec_h = 20
        num_bars = 24
        bar_gap = 3
        avail_w = w - 16
        bar_w = (avail_w - (num_bars - 1) * bar_gap) / num_bars

        for i in range(num_bars):
            bx = 8 + i * (bar_w + bar_gap)

            if self.is_online:
                # Dynamic wave with dual harmonic motion
                wave1 = math.sin(self._phase + i * 0.42)
                wave2 = math.cos(self._phase * 0.7 - i * 0.3)
                norm_height = (wave1 + wave2 + 2.0) / 4.0
                bar_actual_h = max(3.0, norm_height * (spec_h - 3))
            else:
                bar_actual_h = 2.0

            by = spec_y + (spec_h - bar_actual_h)
            brect = QtCore.QRectF(bx, by, bar_w, bar_actual_h)

            if self.is_online:
                grad = QtGui.QLinearGradient(brect.topLeft(), brect.bottomLeft())
                grad.setColorAt(0.0, accent_qcolor)
                grad.setColorAt(1.0, QtGui.QColor(accent_qcolor.red(), accent_qcolor.green(), accent_qcolor.blue(), 50))
                painter.setBrush(QtGui.QBrush(grad))
                painter.setPen(QtCore.Qt.NoPen)
                painter.drawRoundedRect(brect, 1.0, 1.0)

                # Glowing peak cap dot
                cap_y = max(spec_y, by - 2)
                painter.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 1.2))
                painter.drawPoint(QtCore.QPointF(bx + bar_w / 2, cap_y))
            else:
                painter.setBrush(QtGui.QBrush(QtGui.QColor(50, 60, 58, 120)))
                painter.setPen(QtCore.Qt.NoPen)
                painter.drawRoundedRect(brect, 1.0, 1.0)


class McpStatusDiagramBarCard:
    """Virtual diagram bar card representing end-to-end status of the whole MCP stack."""

    def __init__(self, QtCore: Any, QtWidgets: Any, translator: DesktopTranslator) -> None:
        self.QtCore = QtCore
        self.QtWidgets = QtWidgets
        self.translator = translator
        self.accent_color: str = COLORS["lime"]
        self.success_color: str = COLORS["success"]
        self.start_timestamp: float | None = None
        self.is_running: bool = False
        self._last_data: dict[str, Any] = {}

        self.widget = QtWidgets.QFrame()
        self.widget.setObjectName("runtimeLiveClock")
        self.widget.setProperty("role", "card")
        self.widget.setMinimumHeight(135)

        layout = QtWidgets.QVBoxLayout(self.widget)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(5)

        # Header row with title & matrix badge
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title_key = "runtime.mcp_status_matrix"
        title_text = translator.text(title_key)
        if title_text == title_key:
            title_text = "SƠ ĐỒ TRẠNG THÁI TOÀN MCP"
        self.title_label = QtWidgets.QLabel(title_text)
        self.title_label.setProperty("role", "cardTitle")
        self.title_label.setStyleSheet("font-size: 11px; font-weight: 700;")
        header.addWidget(self.title_label)
        header.addStretch(1)

        self.live_badge = QtWidgets.QLabel("● LIVE")
        self.live_badge.setStyleSheet(
            f"color: {self.success_color}; font-size: 9px; font-weight: 800; background: rgba(66, 213, 173, 0.12); "
            f"border: 1px solid {self.success_color}; border-radius: 4px; padding: 1px 5px;"
        )
        header.addWidget(self.live_badge)
        layout.addLayout(header)

        # Virtual Diagram Spectrum Bar
        self.spectrum_bar = McpVirtualSpectrumBar(self.widget)
        layout.addWidget(self.spectrum_bar)

        # Bottom Telemetry ticker row (Compact Uptime, Port, Channel info)
        telemetry_row = QtWidgets.QHBoxLayout()
        telemetry_row.setContentsMargins(0, 2, 0, 0)

        self.uptime_label = QtWidgets.QLabel("UPTIME: --:--:--")
        self.uptime_label.setStyleSheet(
            "font-family: monospace; font-size: 10px; font-weight: 800; color: #81908a;"
        )
        self.clock_display = self.uptime_label  # Alias for compatibility
        telemetry_row.addWidget(self.uptime_label)

        telemetry_row.addStretch(1)

        self.started_label = QtWidgets.QLabel(f"{translator.text('runtime.started_at')}: --:--:--")
        self.telemetry_meta = QtWidgets.QLabel("PORT: 18427 · CH: 4/4")
        self.telemetry_meta.setStyleSheet(
            "font-family: monospace; font-size: 9px; color: #81908a; font-weight: 700;"
        )
        telemetry_row.addWidget(self.telemetry_meta)
        layout.addLayout(telemetry_row)

        # Interval timer for live ticking
        self.timer = QtCore.QTimer(self.widget)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start()

    def update_state(
        self,
        running: bool,
        start_time: float | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        self.is_running = running
        if running:
            if self.start_timestamp is None:
                self.start_timestamp = start_time or time.time()
                started_str = time.strftime("%H:%M:%S", time.localtime(self.start_timestamp))
                self.started_label.setText(f"{self.translator.text('runtime.started_at')}: {started_str}")
            self.live_badge.setText("● LIVE")
            self.live_badge.setStyleSheet(
                f"color: {self.success_color}; font-size: 9px; font-weight: 800; background: rgba(66, 213, 173, 0.12); "
                f"border: 1px solid {self.success_color}; border-radius: 4px; padding: 1px 5px;"
            )
        else:
            self.start_timestamp = None
            self.live_badge.setText("○ OFFLINE")
            self.live_badge.setStyleSheet(
                "color: #81908a; font-size: 9px; font-weight: 800; background: rgba(129, 144, 138, 0.1); "
                "border: 1px solid #81908a; border-radius: 4px; padding: 1px 5px;"
            )
            self.started_label.setText(f"{self.translator.text('runtime.started_at')}: --:--:--")

        if data is not None:
            self._last_data = dict(data)
        elif not running:
            self._last_data = {
                "server": {"running": False},
                "tunnel": {"running": False},
                "bridge": "stopped",
                "workspace": "",
            }
        elif not self._last_data:
            self._last_data = {
                "server": {"running": running},
                "tunnel": {"running": running},
                "bridge": "ready" if running else "stopped",
                "workspace": "/work" if running else "",
            }
        else:
            self._last_data["server"] = {"running": running}

        self.spectrum_bar.set_state(self._last_data, self.accent_color)
        self._update_uptime_display()

    def _on_tick(self) -> None:
        if self.is_running and self.start_timestamp is not None:
            self._update_uptime_display()

    def _update_uptime_display(self) -> None:
        if self.is_running and self.start_timestamp is not None:
            elapsed = max(0, int(time.time() - self.start_timestamp))
            hours = elapsed // 3600
            minutes = (elapsed % 3600) // 60
            seconds = elapsed % 60
            self.uptime_label.setText(f"UPTIME: {hours:02d}:{minutes:02d}:{seconds:02d}")
            self.uptime_label.setStyleSheet(
                f"font-family: monospace; font-size: 10px; font-weight: 800; color: {self.accent_color};"
            )
        else:
            self.uptime_label.setText("UPTIME: --:--:--")
            self.uptime_label.setStyleSheet(
                "font-family: monospace; font-size: 10px; font-weight: 800; color: #81908a;"
            )

    def set_theme(self, theme_colors: dict[str, str]) -> None:
        self.accent_color = theme_colors.get("lime", COLORS["lime"])
        self.success_color = theme_colors.get("success", COLORS["success"])
        self.spectrum_bar.accent_color = self.accent_color
        self.spectrum_bar.update()
        self.update_state(self.is_running, self.start_timestamp, self._last_data)

    def set_translator(self, translator: DesktopTranslator) -> None:
        self.translator = translator
        title_key = "runtime.mcp_status_matrix"
        title_text = translator.text(title_key)
        if title_text == title_key:
            title_text = "SƠ ĐỒ TRẠNG THÁI TOÀN MCP"
        self.title_label.setText(title_text)
        if self.start_timestamp is not None:
            started_str = time.strftime("%H:%M:%S", time.localtime(self.start_timestamp))
            self.started_label.setText(f"{translator.text('runtime.started_at')}: {started_str}")
        else:
            self.started_label.setText(f"{translator.text('runtime.started_at')}: --:--:--")


LiveUptimeClock = McpStatusDiagramBarCard


class SystemTopologyDiagram:
    """Interactive live architecture diagram showing data flow between UCS components."""

    def __init__(self, QtCore: Any, QtWidgets: Any, translator: DesktopTranslator) -> None:
        self.QtCore = QtCore
        self.QtWidgets = QtWidgets
        self.translator = translator

        self.active_color: str = COLORS["lime"]
        self._last_data: dict[str, Any] = {}

        self.widget = QtWidgets.QFrame()
        self.widget.setObjectName("runtimeTopologyDiagram")
        self.widget.setProperty("role", "card")
        layout = QtWidgets.QVBoxLayout(self.widget)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(3)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self.title_label = QtWidgets.QLabel(translator.text("runtime.topology"))
        self.title_label.setProperty("role", "cardTitle")
        self.title_label.setStyleSheet("font-size: 11px; font-weight: 700;")
        header.addWidget(self.title_label)
        header.addStretch(1)
        self.sync_badge = QtWidgets.QLabel("PIPELINE")
        self.sync_badge.setStyleSheet(
            "color: #81908a; font-size: 9px; font-weight: 700; letter-spacing: 1px;"
        )
        header.addWidget(self.sync_badge)
        layout.addLayout(header)

        # 4 Interactive Flow Nodes
        self.nodes: dict[str, dict[str, Any]] = {}
        node_configs = (
            ("client", "🌐", "runtime.flow_client", "HTTPS / SSE Stream"),
            ("tunnel", "⚡", "runtime.flow_tunnel", "Cloudflare / Ngrok Tunnel"),
            ("server", "⚙️", "runtime.flow_server", "FastMCP Bridge (Port 18427)"),
            ("bridge", "📁", "runtime.flow_bridge", "Tool Execution & Workspace"),
        )

        for i, (node_id, icon, name_key, sub_text) in enumerate(node_configs):
            node_frame = QtWidgets.QFrame()
            node_frame.setObjectName(f"topoNode_{node_id}")
            node_frame.setStyleSheet(
                "background: rgba(18, 25, 24, 0.7); border: 1px solid #2a3632; border-radius: 5px;"
            )
            node_layout = QtWidgets.QHBoxLayout(node_frame)
            node_layout.setContentsMargins(8, 3, 8, 3)
            node_layout.setSpacing(6)

            icon_lbl = QtWidgets.QLabel(icon)
            icon_lbl.setStyleSheet("font-size: 12px; background: transparent; border: 0;")
            node_layout.addWidget(icon_lbl)

            text_col = QtWidgets.QVBoxLayout()
            text_col.setContentsMargins(0, 0, 0, 0)
            text_col.setSpacing(0)

            name_lbl = QtWidgets.QLabel(translator.text(name_key))
            name_lbl.setStyleSheet("font-size: 10px; font-weight: 700; background: transparent; border: 0;")
            sub_lbl = QtWidgets.QLabel(sub_text)
            sub_lbl.setStyleSheet("font-size: 9px; color: #81908a; background: transparent; border: 0;")
            text_col.addWidget(name_lbl)
            text_col.addWidget(sub_lbl)
            node_layout.addLayout(text_col, 1)

            dot_lbl = QtWidgets.QLabel("●")
            dot_lbl.setStyleSheet("font-size: 9px; color: #81908a; background: transparent; border: 0;")
            node_layout.addWidget(dot_lbl)

            layout.addWidget(node_frame)
            self.nodes[node_id] = {
                "frame": node_frame,
                "name": name_lbl,
                "name_key": name_key,
                "sub": sub_lbl,
                "dot": dot_lbl,
            }

            if i < len(node_configs) - 1:
                arrow = QtWidgets.QLabel("↓")
                arrow.setAlignment(QtCore.Qt.AlignCenter)
                arrow.setStyleSheet("color: #81908a; font-size: 9px; font-weight: 700; background: transparent; border: 0;")
                layout.addWidget(arrow)

    def render(self, data: dict[str, Any]) -> None:
        self._last_data = dict(data)
        server_running = bool((data.get("server") or {}).get("running"))
        tunnel_running = bool((data.get("tunnel") or {}).get("running"))
        bridge_ready = str(data.get("bridge") or "").lower() in {"ready", "running", "ok"}

        # Client node: active if tunnel or server is up
        client_active = server_running or tunnel_running
        self._update_node("client", client_active, "CONNECTED" if client_active else "IDLE")

        # Tunnel node
        tunnel_url = str(data.get("url") or data.get("last_known_url") or "")
        tunnel_sub = tunnel_url[:32] + "…" if len(tunnel_url) > 32 else (tunnel_url or "Cloudflare / Ngrok Tunnel")
        self._update_node("tunnel", tunnel_running, tunnel_sub)

        # Server node
        server_pid = (data.get("server") or {}).get("pid")
        server_sub = f"PID: {server_pid} · Port 18427" if server_pid else "FastMCP Bridge (Port 18427)"
        self._update_node("server", server_running, server_sub)

        # Bridge node
        ws = str(data.get("workspace") or "")
        ws_sub = ws[-24:] if len(ws) > 24 else (ws or "Tool Execution & Workspace")
        self._update_node("bridge", bridge_ready, ws_sub)

    def _update_node(self, node_id: str, active: bool, sub_text: str) -> None:
        info = self.nodes.get(node_id)
        if not info:
            return
        info["sub"].setText(sub_text)
        if active:
            info["dot"].setText("● ONLINE")
            info["dot"].setStyleSheet(
                f"font-size: 9px; font-weight: 700; color: {self.active_color}; background: transparent; border: 0;"
            )
            info["frame"].setStyleSheet(
                f"background: rgba(18, 25, 24, 0.85); border: 1px solid {self.active_color}; border-radius: 5px;"
            )
        else:
            info["dot"].setText("○ INACTIVE")
            info["dot"].setStyleSheet("font-size: 9px; font-weight: 700; color: #ff6b61; background: transparent; border: 0;")
            info["frame"].setStyleSheet(
                "background: rgba(18, 25, 24, 0.5); border: 1px solid #2a3632; border-radius: 5px;"
            )

    def set_theme(self, theme_colors: dict[str, str]) -> None:
        self.active_color = theme_colors.get("lime", COLORS["lime"])
        if self._last_data:
            self.render(self._last_data)

    def set_translator(self, translator: DesktopTranslator) -> None:
        self.translator = translator
        self.title_label.setText(translator.text("runtime.topology"))
        for info in self.nodes.values():
            info["name"].setText(translator.text(info["name_key"]))


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
        self.live_clock = LiveUptimeClock(QtCore, QtWidgets, translator)
        self.topology_diagram = SystemTopologyDiagram(QtCore, QtWidgets, translator)
        self._build()

    def _build(self) -> None:
        from PySide6 import QtGui

        layout = self.QtWidgets.QGridLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)
        layout.addWidget(self.page_heading.widget, 0, 0, 1, 2)

        self.metric_strip = self.QtWidgets.QFrame()
        self.metric_strip.setObjectName("runtimeMetricStrip")
        self.metric_strip.setProperty("role", "card")
        self.metric_strip.setMinimumHeight(102)
        metric_layout = self.QtWidgets.QHBoxLayout(self.metric_strip)
        metric_layout.setContentsMargins(10, 8, 10, 8)
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
        self.endpoint_value.setWordWrap(True)
        self.endpoint_value.setTextInteractionFlags(self.QtCore.Qt.TextSelectableByMouse)
        self.endpoint_value.setStyleSheet("font-size: 11px; line-height: 1.25;")
        self.copy_button = self.QtWidgets.QPushButton(self.translator.text("action.copy_url"))
        self.copy_button.setObjectName("runtimeCopyEndpointButton")
        self.copy_button.setProperty("role", "compactAction")
        self.copy_button.setFixedHeight(26)
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
        self.summary_label.setAlignment(self.QtCore.Qt.AlignTop | self.QtCore.Qt.AlignLeft)
        self.summary_label.setStyleSheet("font-size: 12px; line-height: 1.35;")
        self.metric_cells.append(signal_metric)

        for metric, stretch in zip(self.metric_cells, (2, 3, 4), strict=True):
            metric.widget.setSizePolicy(
                self.QtWidgets.QSizePolicy.Expanding,
                self.QtWidgets.QSizePolicy.Preferred,
            )
            metric_layout.addWidget(metric.widget, stretch)
        # Keep this alias for callers that previously only needed the overview frame.
        self.health_strip = self.metric_strip
        layout.addWidget(self.metric_strip, 1, 0, 1, 2)

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
                ("field.runtime_status", "field.authentication"),
            ),
            (
                "field.server",
                self.server_value,
                ("field.runtime_status", "runtime.status_summary"),
            ),
            (
                "field.tunnel",
                self.tunnel_value,
                ("field.runtime_status", "runtime.status_summary"),
            ),
        ):
            card = ServiceDetailCard(self.QtWidgets, self.translator.text(title_key))
            card.widget.setSizePolicy(
                self.QtWidgets.QSizePolicy.Expanding,
                self.QtWidgets.QSizePolicy.Preferred,
            )
            card.widget.minimumSizeHint = lambda: self.QtCore.QSize(160, 100)
            card.widget.setMinimumHeight(135)
            card.layout.removeWidget(card.title)
            header = self.QtWidgets.QHBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            icon_label = self.QtWidgets.QLabel()
            icon_label.setPixmap(
                _service_icon_pixmap(self.QtCore, QtGui, len(self.service_cards))
            )
            icon_label.setFixedSize(24, 24)
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
                    vertical=(detail_key == "runtime.status_summary"),
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
        layout.addLayout(self.service_grid, 2, 0)

        self.workspace_frame = self.QtWidgets.QFrame()
        self.workspace_frame.setObjectName("runtimeWorkspaceFrame")
        self.workspace_frame.setProperty("role", "card")
        workspace_row = self.QtWidgets.QHBoxLayout(self.workspace_frame)
        workspace_row.setContentsMargins(10, 6, 10, 6)
        workspace_row.setSpacing(8)
        self.workspace_label = self.QtWidgets.QLabel(
            self.translator.text("field.workspace")
        )
        self.workspace_label.setProperty("role", "cardTitle")
        workspace_row.addWidget(self.workspace_label)
        workspace_row.addWidget(self.workspace_value, 1)
        self.workspace_value.setFixedHeight(30)
        self.choose_button = self.QtWidgets.QPushButton(
            self.translator.text("action.choose_folder")
        )
        self.choose_button.setObjectName("runtimeChooseWorkspaceButton")
        self.choose_button.clicked.connect(self.callbacks.choose_workspace)
        self.choose_button.setFixedHeight(28)
        self.apply_button = self.QtWidgets.QPushButton(self.translator.text("action.apply"))
        self.apply_button.setObjectName("runtimeApplyWorkspaceButton")
        self.apply_button.clicked.connect(self.callbacks.apply_workspace)
        self.apply_button.setFixedHeight(28)
        apply_button_variant(self.choose_button, "secondary")
        apply_button_variant(self.apply_button, "primary")
        self.workspace_buttons = [self.choose_button, self.apply_button]
        workspace_row.addWidget(self.choose_button)
        workspace_row.addWidget(self.apply_button)
        layout.addWidget(self.workspace_frame, 3, 0)

        self.action_dock = self.QtWidgets.QFrame()
        self.action_dock.setObjectName("runtimeActionDock")
        self.action_dock.setProperty("role", "card")
        action_row = self.QtWidgets.QHBoxLayout(self.action_dock)
        action_row.setContentsMargins(10, 6, 10, 6)
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
            button.setFixedHeight(30)
            apply_button_variant(button, variant)
            button.setSizePolicy(
                self.QtWidgets.QSizePolicy.Expanding,
                self.QtWidgets.QSizePolicy.Preferred,
            )
            action_row.addWidget(button, 1)
        self.stop_button.setObjectName("runtimeStopButton")
        self.stop_button.clicked.connect(self.callbacks.stop)
        self.stop_button.setFixedHeight(30)
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
        layout.addWidget(self.action_dock, 4, 0)

        # Right column: Live operations chronometer clock & system topology diagram
        self.live_clock.widget.setMaximumWidth(300)
        self.topology_diagram.widget.setMaximumWidth(300)
        layout.addWidget(self.live_clock.widget, 2, 1)
        layout.addWidget(self.topology_diagram.widget, 3, 1, 2, 1)

        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 0)
        layout.setRowStretch(5, 1)

    def render(self, data: dict[str, Any]) -> RuntimePresentation:
        self.latest_data = dict(data)
        presentation = runtime_presentation(data, self.translator)
        server_running = bool((data.get("server") or {}).get("running"))
        self.live_clock.update_state(server_running, data=data)
        self.topology_diagram.render(data)
        self.status_label.setText(presentation.status)
        self.summary_label.setText(presentation.summary)
        self.summary_label.setToolTip(presentation.summary)
        self.summary_label.setStyleSheet(
            f"color: {presentation.color}; font-size: 12px; line-height: 1.35; background: transparent; border: 0;"
        )
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
                (presentation.bridge, presentation.authentication),
                (presentation.server, presentation.summary),
                (presentation.tunnel, presentation.summary),
            ),
            strict=True,
        ):
            for label, text in zip(detail_values, values, strict=True):
                label.setText(text)
                label.setToolTip(text)
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
        self.live_clock.set_translator(translator)
        self.topology_diagram.set_translator(translator)
        self.start_button.setText(translator.text("action.start"))
        self.stop_button.setText(translator.text("action.stop"))
        self.restart_button.setText(translator.text("action.restart"))
        self.refresh_button.setText(translator.text("action.refresh"))
        self.copy_button.setText(translator.text("action.copy_url"))
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
            self.live_clock.update_state(False)
            self.topology_diagram.render({})
            self.status_label.setText(translator.text("status.loading"))
            self.summary_label.setText(translator.text("status.not_available"))
            self.summary_label.setToolTip("")
            self.summary_label.setStyleSheet("font-size: 12px; line-height: 1.35; background: transparent; border: 0;")
            self.endpoint_value.setText(translator.text("status.not_available"))
            self.bridge_value.setText(translator.text("status.not_available"))
            self.server_value.setText(translator.text("status.not_available"))
            self.tunnel_value.setText(translator.text("status.not_available"))
            for detail_values in self._service_detail_values:
                for value in detail_values[1:]:
                    value.setText(translator.text("status.not_available"))

    def set_theme(self, theme: str) -> None:
        from PySide6 import QtGui
        from app.cli.desktop_qt.theme import THEMES
        theme_colors = THEMES.get(theme, COLORS)
        accent = theme_colors.get("lime", COLORS["lime"])
        for i, icon_label in enumerate(self.service_icon_labels):
            icon_label.setPixmap(_service_icon_pixmap(self.QtCore, QtGui, i, color=accent))
        self.live_clock.set_theme(theme_colors)
        self.topology_diagram.set_theme(theme_colors)
        self.status_pill.set_theme_accent(accent)
        for pill in self.service_pills:
            pill.set_theme_accent(accent)
