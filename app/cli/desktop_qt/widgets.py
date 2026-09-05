from __future__ import annotations

from typing import Any

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
        self.layout.setContentsMargins(12, 10, 12, 10)
        self.layout.setSpacing(8)
        self.title = QtWidgets.QLabel(title)
        self.title.setProperty("role", "sectionTitle")
        if title:
            self.layout.addWidget(self.title)


class DetailRow:
    """Static detail label/value row with no data derivation."""

    def __init__(self, QtWidgets: Any, label: str, value: str) -> None:
        self.widget = QtWidgets.QFrame()
        self.widget.setObjectName("detailRow")
        self.layout = QtWidgets.QHBoxLayout(self.widget)
        self.layout.setContentsMargins(8, 6, 8, 6)
        self.layout.setSpacing(8)
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


class StatusPill:
    def __init__(self, QtWidgets: Any, text: str = "") -> None:
        self.widget = QtWidgets.QLabel(text)
        self.widget.setProperty("role", "pill")
        self.widget.setProperty("state", "loading")
        self.widget.setObjectName("statusPill")
        self.widget.setMinimumHeight(28)
        self.widget.setMargin(8)

    def set_state(self, text: str, visual_state: str) -> None:
        self.widget.setText(text)
        self.widget.setProperty("state", visual_state)
        self.widget.style().unpolish(self.widget)
        self.widget.style().polish(self.widget)


class RailButton:
    def __init__(self, QtWidgets: Any, text: str, callback: Any) -> None:
        self.button = QtWidgets.QPushButton(text)
        self.button.setProperty("role", "rail")
        self.button.clicked.connect(callback)

    def set_active(self, active: bool) -> None:
        self.button.setProperty("active", "true" if active else "false")
        self.button.style().unpolish(self.button)
        self.button.style().polish(self.button)
