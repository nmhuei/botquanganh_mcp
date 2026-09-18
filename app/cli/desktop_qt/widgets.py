from __future__ import annotations

import math
from typing import Any

from PySide6 import QtCore, QtGui, QtSvg, QtWidgets

from app.cli.desktop_identity import desktop_app_icon_path
from app.cli.desktop_identity import DESKTOP_APP_NAME, DESKTOP_IDENTITY_TEXT
from app.cli.desktop_qt.theme import COLORS, LAYOUT


def load_logo_pixmap(QtGui: Any, size: int = 52) -> Any | None:
    path = desktop_app_icon_path()
    if not path.is_file():
        return None
    pixmap = QtGui.QPixmap(str(path))
    if pixmap.isNull():
        return None
    return pixmap.scaled(size, size, QtGui.Qt.KeepAspectRatio, QtGui.Qt.SmoothTransformation)


def apply_button_variant(button: Any, variant: str) -> Any:
    button.setProperty("variant", variant)
    button.style().unpolish(button)
    button.style().polish(button)
    return button


class HeaderBrand:
    """Reusable compact UCS identity block backed by the canonical logo asset."""

    def __init__(self, QtWidgets: Any, QtGui: Any) -> None:
        self.widget = QtWidgets.QFrame()
        self.widget.setObjectName("commandBrand")
        layout = QtWidgets.QHBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(LAYOUT["space_sm"])
        self.logo = QtWidgets.QLabel()
        self.logo.setAccessibleName(DESKTOP_APP_NAME)
        pixmap = load_logo_pixmap(QtGui, 46)
        if pixmap is not None:
            self.logo.setPixmap(pixmap)
            self.logo.setFixedSize(46, 46)
            self.logo.setAlignment(QtGui.Qt.AlignCenter)
        layout.addWidget(self.logo)
        labels = QtWidgets.QVBoxLayout()
        labels.setContentsMargins(0, 0, 0, 0)
        labels.setSpacing(0)
        self.app_name_label = QtWidgets.QLabel(DESKTOP_APP_NAME)
        self.app_name_label.setProperty("role", "brandName")
        self.identity_label = QtWidgets.QLabel(DESKTOP_IDENTITY_TEXT)
        self.identity_label.setProperty("role", "brandIdentity")
        labels.addWidget(self.app_name_label)
        labels.addWidget(self.identity_label)
        layout.addLayout(labels)


class IconRailItem:
    """Icon-first route control that keeps a readable accessible route name."""

    def __init__(self, QtWidgets: Any, route_name: str, glyph: str, callback: Any) -> None:
        self.button = QtWidgets.QPushButton(glyph)
        self.button.setObjectName("iconRailItem")
        self.button.setAccessibleName(route_name)
        self.button.setToolTip(route_name)
        self.button.clicked.connect(callback)
        self.set_active(True)

    def set_active(self, active: bool) -> None:
        self.button.setProperty("active", "true" if active else "false")
        self.button.style().unpolish(self.button)
        self.button.style().polish(self.button)


class SectionHeading:
    """Small title and optional eyebrow used above dense command panels."""

    def __init__(self, QtWidgets: Any, title: str, eyebrow: str = "") -> None:
        self.widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.eyebrow_label = QtWidgets.QLabel(eyebrow)
        self.eyebrow_label.setProperty("role", "sectionEyebrow")
        self.title_label = QtWidgets.QLabel(title)
        self.title_label.setProperty("role", "sectionTitle")
        if eyebrow:
            layout.addWidget(self.eyebrow_label)
        layout.addWidget(self.title_label)


class PanelFrame:
    """Framed panel with a ready-to-use compact vertical layout."""

    def __init__(self, QtWidgets: Any) -> None:
        self.widget = QtWidgets.QFrame()
        self.widget.setObjectName("panelFrame")
        self.layout = QtWidgets.QVBoxLayout(self.widget)
        self.layout.setContentsMargins(
            LAYOUT["space_lg"], LAYOUT["space_md"], LAYOUT["space_lg"], LAYOUT["space_md"]
        )
        self.layout.setSpacing(LAYOUT["space_sm"])


class FooterStatusItem:
    """Footer text primitive for compact backend and refresh state."""

    def __init__(self, QtWidgets: Any, text: str = "") -> None:
        self.widget = QtWidgets.QLabel(text)
        self.widget.setProperty("role", "footerStatus")


class UcsCard:
    def __init__(self, QtWidgets: Any, title: str = "") -> None:
        self.widget = QtWidgets.QFrame()
        self.widget.setProperty("role", "card")
        self.layout = QtWidgets.QVBoxLayout(self.widget)
        self.layout.setContentsMargins(16, 14, 16, 14)
        self.layout.setSpacing(8)
        self.title = QtWidgets.QLabel(title)
        self.title.setProperty("role", "cardTitle")
        if title:
            self.layout.addWidget(self.title)


class MetricCell:
    """Static metric label/value presentation without service-state behavior."""

    def __init__(self, QtWidgets: Any, label: str, value: str) -> None:
        self.widget = QtWidgets.QFrame()
        self.widget.setObjectName("metricCell")
        self.layout = QtWidgets.QVBoxLayout(self.widget)
        self.layout.setContentsMargins(12, 8, 12, 8)
        self.layout.setSpacing(2)
        self.label = QtWidgets.QLabel(label)
        self.label.setProperty("role", "metricLabel")
        self.value = QtWidgets.QLabel(value)
        self.value.setProperty("role", "metricValue")
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.value)


class ServiceDetailCard:
    """Static service-detail container that leaves all state to its caller."""

    def __init__(self, QtWidgets: Any, title: str = "") -> None:
        self.widget = QtWidgets.QFrame()
        self.widget.setObjectName("serviceDetailCard")
        self.layout = QtWidgets.QVBoxLayout(self.widget)
        self.layout.setContentsMargins(10, 8, 10, 8)
        self.layout.setSpacing(6)
        self.title = QtWidgets.QLabel(title)
        self.title.setProperty("role", "sectionTitle")
        if title:
            self.layout.addWidget(self.title)


class DetailRow:
    """Static detail label/value row with no data derivation."""

    def __init__(
        self, QtWidgets: Any, label: str, value: str, vertical: bool = False
    ) -> None:
        self.widget = QtWidgets.QFrame()
        self.widget.setObjectName("detailRow")
        if vertical:
            self.layout = QtWidgets.QVBoxLayout(self.widget)
            self.layout.setContentsMargins(8, 4, 8, 5)
            self.layout.setSpacing(3)
            self.label = QtWidgets.QLabel(label)
            self.label.setProperty("role", "detailLabel")
            self.value = QtWidgets.QLabel(value)
            self.value.setProperty("role", "detailValue")
            self.value.setWordWrap(True)
            self.layout.addWidget(self.label)
            self.layout.addWidget(self.value)
        else:
            self.layout = QtWidgets.QHBoxLayout(self.widget)
            self.layout.setContentsMargins(8, 4, 8, 5)
            self.layout.setSpacing(6)
            self.label = QtWidgets.QLabel(label)
            self.label.setProperty("role", "detailLabel")
            self.value = QtWidgets.QLabel(value)
            self.value.setProperty("role", "detailValue")
            self.layout.addWidget(self.label)
            self.layout.addWidget(self.value, 1)


class InspectorFrame:
    """Static inspector frame that accepts presentation widgets from a caller."""

    def __init__(self, QtWidgets: Any, title: str = "") -> None:
        self.widget = QtWidgets.QFrame()
        self.widget.setObjectName("inspectorSurface")
        self.layout = QtWidgets.QVBoxLayout(self.widget)
        self.layout.setContentsMargins(12, 10, 12, 12)
        self.layout.setSpacing(8)
        self.title = QtWidgets.QLabel(title)
        self.title.setProperty("role", "sectionEyebrow")
        if title:
            self.layout.addWidget(self.title)


CHATGPT_SVG_PATH = (
    "M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9"
    "A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9"
    " 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107"
    " 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24"
    "a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001"
    " 6.0557 6.0557 0 0 0-.7475-7.073zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408"
    "l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369"
    "l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.5045 4.5045 0 0 1-4.4945 4.4944zm-9.6607-4.1254"
    "a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0"
    "l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502"
    "a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728"
    "V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685"
    "a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.8956zm16.0993 3.8558"
    "L12.5973 8.3829 14.6174 7.2144a.0757.0757 0 0 1 .071 0l4.8303 2.7913"
    "a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.4021-.6813zm2.0107-3.0231"
    "l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297"
    "V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.6608zm-11.4587 3.518"
    "L12 10.4578l2.9972 1.7303v3.4607L12 17.3791l-2.9972-1.7303z"
)


def _render_status_icon(kind: str, color: str, size: int = 16) -> QtGui.QPixmap:
    """Render crisp vector icon for the status pill."""
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.transparent)
    if kind == "chatgpt":
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="{color}"><g transform="translate(1,1) scale(0.92)"><path d="{CHATGPT_SVG_PATH}"/></g></svg>"""
    elif kind == "hazard":
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
          <polygon points="12,3.2 2.8,20.2 21.2,20.2" fill="{color}" stroke="{color}" stroke-width="1.0" stroke-linejoin="round"/>
          <polygon points="12,8 6.5,18 17.5,18" fill="#090d0c"/>
          <polygon points="12,10.5 8,16.5 16,16.5" fill="{color}"/>
        </svg>"""
    elif kind == "tool":
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
          <circle cx="17.5" cy="6.5" r="0.6" fill="{color}"/>
        </svg>"""
    else:
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.5" fill="{color}"/></svg>"""

    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(svg.encode("utf-8")))
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    return pixmap


class BeaconDot(QtWidgets.QWidget):
    """Pulsating status beacon dot with smooth breathing halo effect."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self.color = QtGui.QColor("#42d5ad")
        self.phase = 0.0

    def set_color(self, hex_color: str) -> None:
        self.color = QtGui.QColor(hex_color)
        self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        breath = (math.sin(self.phase) + 1.0) / 2.0  # 0.0 -> 1.0

        # Outer breathing halo
        halo_alpha = int(35 + breath * 145)
        halo_color = QtGui.QColor(self.color)
        halo_color.setAlpha(halo_alpha)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(halo_color)
        halo_radius = 3.0 + breath * 2.2
        painter.drawEllipse(QtCore.QPointF(6, 6), halo_radius, halo_radius)

        # Inner solid core LED dot
        core_color = QtGui.QColor(self.color)
        core_color.setAlpha(int(210 + breath * 45))
        painter.setBrush(core_color)
        painter.drawEllipse(QtCore.QPointF(6, 6), 2.5, 2.5)
        painter.end()


class StatusPillWidget(QtWidgets.QFrame):
    """Cyberpunk command center status capsule pill with breathing glow and status icons."""

    def __init__(self, text: str = "", parent: Any = None) -> None:
        super().__init__(parent)
        self.setObjectName("statusPill")
        self.setProperty("role", "pill")
        self.setProperty("state", "loading")
        self.setMinimumHeight(26)
        self.setMaximumHeight(30)
        self.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 6, 2)
        layout.setSpacing(3)

        self.beacon = BeaconDot(self)
        layout.addWidget(self.beacon)

        self.icon_label = QtWidgets.QLabel(self)
        self.icon_label.setFixedSize(16, 16)
        self.icon_label.setAlignment(QtCore.Qt.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent; border: 0;")
        layout.addWidget(self.icon_label)

        self.text_label = QtWidgets.QLabel(text, self)
        self.text_label.setStyleSheet("font-weight: 700; font-size: 11px; background: transparent; border: 0; padding: 0 1px;")
        layout.addWidget(self.text_label)

        self.theme_accent: str | None = None
        self.phase = 0.0
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(40)  # 25 FPS breathing pulse

        self._update_appearance("loading", text)

    def set_theme_accent(self, color: str | None) -> None:
        self.theme_accent = color
        self._update_appearance(str(self.property("state") or "loading"))

    def _on_tick(self) -> None:
        self.phase += 0.08
        self.beacon.phase = self.phase
        self.beacon.update()

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        if not self.timer.isActive():
            self.timer.start(40)

    def hideEvent(self, event: Any) -> None:
        super().hideEvent(event)
        if self.timer.isActive():
            self.timer.stop()

    def text(self) -> str:
        return self.text_label.text()

    def setText(self, text: str) -> None:
        self.text_label.setText(text)
        self._update_appearance(str(self.property("state") or "loading"), text)

    def set_state(self, text: str, visual_state: str) -> None:
        self.text_label.setText(text)
        self.setProperty("state", visual_state)
        self._update_appearance(visual_state, text)
        self.style().unpolish(self)
        self.style().polish(self)
        self.adjustSize()

    def _update_appearance(self, visual_state: str, text: str = "") -> None:
        raw_state = str(visual_state).casefold()
        text_lower = (text or self.text_label.text()).casefold()

        # Determine normalized state: ready vs stopped vs malfunction/warning
        if raw_state in ("ready", "success", "running") or "sẵn sàng" in text_lower or "ready" in text_lower:
            color = self.theme_accent or "#42d5ad"
            icon_kind = "chatgpt"
            border_color = color
            bg_color = "#0e1513"
        elif raw_state in ("stopped",) or "đã dừng" in text_lower or "dừng" in text_lower or "stopped" in text_lower:
            color = "#ff4d4d"
            icon_kind = "hazard"
            border_color = "rgba(255, 77, 77, 0.55)"
            bg_color = "#150e0e"
        elif raw_state in ("error", "warning", "warn", "needs_attention") or "chú ý" in text_lower or "attention" in text_lower or "lỗi" in text_lower:
            color = "#f4b942"
            icon_kind = "tool"
            border_color = "rgba(244, 185, 66, 0.5)"
            bg_color = "#15130e"
        else:
            color = "#a9b5af"
            icon_kind = "dot"
            border_color = "#2a3632"
            bg_color = "#0e1513"

        self.beacon.set_color(color)
        self.icon_label.setPixmap(_render_status_icon(icon_kind, color, 16))
        self.text_label.setStyleSheet(f"color: {color}; font-weight: 700; font-size: 11px; background: transparent; border: 0;")
        self.setStyleSheet(f"""
        QFrame#statusPill {{
            background-color: {bg_color};
            border: 1px solid {border_color};
            border-radius: 14px;
        }}
        """)


class StatusPill:
    """Status indicator capsule with breathing beacon dot and context icon."""

    def __init__(self, QtWidgets: Any, text: str = "") -> None:
        self.widget = StatusPillWidget(text=text)

    def set_state(self, text: str, visual_state: str) -> None:
        self.widget.set_state(text, visual_state)

    def set_theme_accent(self, color: str | None) -> None:
        self.widget.set_theme_accent(color)


class RailButton:
    def __init__(self, QtWidgets: Any, text: str, callback: Any) -> None:
        self.button = QtWidgets.QPushButton(text)
        self.button.setProperty("role", "rail")
        self.button.clicked.connect(callback)

    def set_active(self, active: bool) -> None:
        self.button.setProperty("active", "true" if active else "false")
        self.button.style().unpolish(self.button)
        self.button.style().polish(self.button)
