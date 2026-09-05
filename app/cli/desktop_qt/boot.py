"""Non-blocking Qt splash screen for the UCS desktop application."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.cli.desktop_identity import DESKTOP_APP_NAME, DESKTOP_IDENTITY_TEXT
from app.cli.desktop_qt.theme import COLORS
from app.cli.desktop_qt.widgets import load_logo_pixmap
from app.cli.desktop_views.boot import BOOT_PHASES


QT_BOOT_TOTAL_MS = 3000


def phase_delay_ms() -> int:
    return QT_BOOT_TOTAL_MS // len(BOOT_PHASES)


class QtBootSplash:
    """Advance existing boot phases without blocking the Qt event loop."""

    def __init__(
        self,
        QtCore: Any,
        QtGui: Any,
        QtWidgets: Any,
        on_ready: Callable[[], None],
    ) -> None:
        self.QtCore = QtCore
        self.QtGui = QtGui
        self.QtWidgets = QtWidgets
        self.on_ready = on_ready
        self.index = -1
        self.closed = False
        self.window = QtWidgets.QWidget()
        self.window.setWindowTitle(DESKTOP_APP_NAME)
        self.window.setFixedSize(680, 360)
        self.window.setObjectName("splashRoot")
        layout = QtWidgets.QVBoxLayout(self.window)
        layout.setContentsMargins(36, 32, 36, 32)
        logo = QtWidgets.QLabel()
        pixmap = load_logo_pixmap(QtGui, 82)
        if pixmap is not None:
            logo.setPixmap(pixmap)
        layout.addWidget(logo, alignment=QtCore.Qt.AlignHCenter)
        title = QtWidgets.QLabel(DESKTOP_APP_NAME)
        title.setAlignment(QtCore.Qt.AlignHCenter)
        identity = QtWidgets.QLabel(DESKTOP_IDENTITY_TEXT)
        identity.setAlignment(QtCore.Qt.AlignHCenter)
        self.phase = QtWidgets.QLabel("")
        self.phase.setAlignment(QtCore.Qt.AlignHCenter)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, len(BOOT_PHASES))
        layout.addWidget(title)
        layout.addWidget(identity)
        layout.addStretch(1)
        layout.addWidget(self.phase)
        layout.addWidget(self.progress)
        self.window.setStyleSheet(
            f"QWidget#splashRoot {{ background: {COLORS['canvas']}; color: {COLORS['text']}; }}"
            f"QProgressBar {{ border: 1px solid {COLORS['border']}; border-radius: 6px; }}"
            f"QProgressBar::chunk {{ background: {COLORS['lime']}; }}"
        )

    def start(self) -> None:
        self.window.show()
        self._advance()

    def close(self) -> None:
        self.closed = True
        self.window.close()

    def _advance(self) -> None:
        if self.closed:
            return
        self.index += 1
        if self.index >= len(BOOT_PHASES):
            self.close()
            self.on_ready()
            return
        self.phase.setText(BOOT_PHASES[self.index])
        self.progress.setValue(self.index + 1)
        self.QtCore.QTimer.singleShot(phase_delay_ms(), self._advance)
