"""Non-blocking Qt splash screen for the UCS desktop application."""

from __future__ import annotations

from collections.abc import Callable
import math
import random
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from app.cli.desktop_identity import DESKTOP_APP_NAME, DESKTOP_IDENTITY_TEXT
from app.cli.desktop_qt.theme import COLORS
from app.cli.desktop_qt.widgets import load_logo_pixmap
from app.cli.desktop_views.boot import BOOT_PHASES


QT_BOOT_TOTAL_MS = 3000


def phase_delay_ms() -> int:
    return QT_BOOT_TOTAL_MS // len(BOOT_PHASES)


PHASE_CYBER_MESSAGES = [
    "[01/04] > INITIALIZING INTERFACE // SCANNING NEURAL ICE...",
    "[02/04] > LOADING WORKSPACES // DECRYPTING HOST MATRIX...",
    "[03/04] > CONNECTING ACTIVITY STREAM // INJECTING PAYLOAD...",
    "[04/04] > SYSTEM READY // BREACH PROTOCOL COMPLETE",
]


class CyberdeckRamBar(QtWidgets.QWidget):
    """Cyberpunk 2077 Cyberdeck RAM hack bar with 16 segmented units, glowing pulse, and bus telemetry."""

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        total_units: int = 16,
    ) -> None:
        super().__init__(parent)
        self.total_units = total_units
        self._minimum = 0
        self._maximum = total_units
        self._value = 0
        self._current_units = 0.0
        self._pulse_phase = 0.0

        self.setFixedHeight(64)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(30)  # ~33 FPS
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    def _on_tick(self) -> None:
        self._pulse_phase += 0.15
        span = max(1, self._maximum - self._minimum)
        target = ((self._value - self._minimum) / span) * self.total_units
        diff = target - self._current_units
        if abs(diff) > 0.08:
            self._current_units += diff * 0.25
        else:
            self._current_units = target
        self.update()

    def setRange(self, minimum: int, maximum: int) -> None:
        self._minimum = minimum
        self._maximum = max(minimum + 1, maximum)
        self.update()

    def setValue(self, value: int) -> None:
        self._value = max(self._minimum, min(value, self._maximum))
        # If jumping for the first time or large jump in tests, update current units immediately
        if self._current_units == 0.0 and self._value > 0:
            span = max(1, self._maximum - self._minimum)
            self._current_units = ((self._value - self._minimum) / span) * self.total_units
        self.update()

    def value(self) -> int:
        return self._value

    def minimum(self) -> int:
        return self._minimum

    def maximum(self) -> int:
        return self._maximum

    def setMinimum(self, minimum: int) -> None:
        self.setRange(minimum, self._maximum)

    def setMaximum(self, maximum: int) -> None:
        self.setRange(self._minimum, maximum)

    def text(self) -> str:
        span = max(1, self._maximum - self._minimum)
        ratio = (self._value - self._minimum) / span
        return f"{int(round(ratio * 100))}%"

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        active_count = int(round(self._current_units))
        active_count = min(active_count, self.total_units)

        # 1. Top Telemetry Row: [CYBERDECK RAM] | [ACTIVE UNITS] | [BUS TELEMETRY]
        font_mono = QtGui.QFont("Monospace", 8, QtGui.QFont.Bold)
        font_mono.setStyleHint(QtGui.QFont.Monospace)
        painter.setFont(font_mono)

        painter.setPen(QtGui.QColor("#00f0ff"))
        painter.drawText(0, 11, "CYBERDECK RAM //")

        painter.setPen(QtGui.QColor("#fcee0a"))
        painter.drawText(116, 11, f"[{active_count:02d} / {self.total_units:02d}] BUFFER UNITS")

        painter.setPen(QtGui.QColor("#00f0ff"))
        right_text = "BUS: 18427 MHz // ICE: BYPASSED"
        painter.drawText(
            QtCore.QRectF(0, 0, w, 12),
            QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter,
            right_text,
        )

        # 2. 16 Segmented RAM Blocks
        block_y = 18
        block_h = 24
        gap = 5
        total_gaps = (self.total_units - 1) * gap
        block_w = (w - total_gaps) / self.total_units

        pulse_alpha = int(170 + 85 * math.sin(self._pulse_phase))  # 85..255

        for i in range(self.total_units):
            bx = i * (block_w + gap)
            rect = QtCore.QRectF(bx, block_y, block_w, block_h)

            if i < active_count:
                # Fully charged block (Cyberpunk Neon Cyan Gradient)
                gradient = QtGui.QLinearGradient(rect.topLeft(), rect.bottomLeft())
                gradient.setColorAt(0.0, QtGui.QColor("#00f0ff"))
                gradient.setColorAt(0.6, QtGui.QColor("#00a2cc"))
                gradient.setColorAt(1.0, QtGui.QColor("#006080"))
                painter.setBrush(QtGui.QBrush(gradient))
                painter.setPen(QtGui.QPen(QtGui.QColor("#d4ffff"), 1.2))
                painter.drawRoundedRect(rect, 3.0, 3.0)

                # Unit number inside block
                painter.setPen(QtGui.QColor("#021018"))
                font_num = QtGui.QFont("Monospace", 8, QtGui.QFont.Black)
                font_num.setStyleHint(QtGui.QFont.Monospace)
                painter.setFont(font_num)
                painter.drawText(rect, QtCore.Qt.AlignCenter, f"{i + 1:02d}")

            elif i == active_count and active_count < self.total_units:
                # Charging unit (Animated Cyberpunk Electric Yellow)
                glow_color = QtGui.QColor(252, 238, 10, pulse_alpha)
                painter.setBrush(QtGui.QBrush(QtGui.QColor(252, 238, 10, int(pulse_alpha * 0.28))))
                painter.setPen(QtGui.QPen(glow_color, 1.5))
                painter.drawRoundedRect(rect, 3.0, 3.0)

                # Diagonal hazard stripes inside charging block (clipped to rect)
                painter.save()
                painter.setClipRect(rect)
                painter.setPen(QtGui.QPen(QtGui.QColor(252, 238, 10, int(pulse_alpha * 0.4)), 1.0))
                for sx in range(int(bx) - 10, int(bx + block_w) + 10, 6):
                    painter.drawLine(sx, int(block_y + block_h), sx + 6, int(block_y))
                painter.restore()

                painter.setPen(glow_color)
                font_charge = QtGui.QFont("Monospace", 8, QtGui.QFont.Bold)
                font_charge.setStyleHint(QtGui.QFont.Monospace)
                painter.setFont(font_charge)
                painter.drawText(rect, QtCore.Qt.AlignCenter, ">>")

            else:
                # Inactive slot
                painter.setBrush(QtGui.QBrush(QtGui.QColor(0, 240, 255, 8)))
                painter.setPen(QtGui.QPen(QtGui.QColor(0, 240, 255, 30), 1.0))
                painter.drawRoundedRect(rect, 3.0, 3.0)

                painter.setPen(QtGui.QColor(0, 240, 255, 55))
                font_dot = QtGui.QFont("Monospace", 7)
                font_dot.setStyleHint(QtGui.QFont.Monospace)
                painter.setFont(font_dot)
                painter.drawText(rect, QtCore.Qt.AlignCenter, "·")

        # 3. Bottom Hex / Memory Offset Ticker
        painter.setFont(QtGui.QFont("Monospace", 7))
        painter.setPen(QtGui.QColor("#255058"))
        offset_hex = f"0x{0x7000 + active_count * 0x0100:04X}"
        bottom_text = f"MEM_OFFSET: {offset_hex} // BUFFER_ALLOCATION: OK // NET_SECURITY: BYPASS"
        painter.drawText(0, h - 2, bottom_text)


class GlitchHeaderCenterWidget(QtWidgets.QWidget):
    """Cyberpunk Logo Scanner Reticle and Chromatic Aberration Glitch Title."""

    def __init__(
        self,
        logo_pixmap: QtGui.QPixmap | None,
        title: str,
        subtitle: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.logo_pixmap = logo_pixmap
        self.title = title
        self.subtitle = subtitle
        self.setFixedHeight(140)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self._reticle_angle = 0.0
        self._glitch_active = False
        self._glitch_shift_x = 0
        self._glitch_shift_y = 0

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(40)  # 25 FPS
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    def _on_tick(self) -> None:
        self._reticle_angle = (self._reticle_angle + 1.2) % 360.0
        if random.random() < 0.15:
            self._glitch_active = True
            self._glitch_shift_x = random.choice([-3, -2, 2, 3])
            self._glitch_shift_y = random.choice([-1, 0, 1])
        else:
            self._glitch_active = False
            self._glitch_shift_x = 0
            self._glitch_shift_y = 0
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        w = self.width()
        cx = w / 2

        # 1. Scanner HUD Reticle around Logo
        reticle_y = 38
        reticle_r = 44

        # Outer segmented rotating arc
        painter.save()
        painter.translate(cx, reticle_y)
        painter.rotate(self._reticle_angle)
        pen_reticle = QtGui.QPen(QtGui.QColor(0, 240, 255, 120), 1.5)
        painter.setPen(pen_reticle)
        for angle in (0, 90, 180, 270):
            painter.drawArc(-reticle_r, -reticle_r, reticle_r * 2, reticle_r * 2, int((angle + 10) * 16), int(70 * 16))
        painter.restore()

        # Static HUD crosshairs / ticks
        painter.setPen(QtGui.QPen(QtGui.QColor(252, 238, 10, 180), 1.2))
        tick_len = 6
        painter.drawLine(int(cx - reticle_r - 2), int(reticle_y), int(cx - reticle_r - 2 - tick_len), int(reticle_y))
        painter.drawLine(int(cx + reticle_r + 2), int(reticle_y), int(cx + reticle_r + 2 + tick_len), int(reticle_y))
        painter.drawLine(int(cx), int(reticle_y - reticle_r - 2), int(cx), int(reticle_y - reticle_r - 2 - tick_len))
        painter.drawLine(int(cx), int(reticle_y + reticle_r + 2), int(cx), int(reticle_y + reticle_r + 2 + tick_len))

        # 2. Draw Center Logo Pixmap
        if self.logo_pixmap is not None:
            pw = self.logo_pixmap.width()
            ph = self.logo_pixmap.height()
            painter.drawPixmap(int(cx - pw / 2), int(reticle_y - ph / 2), self.logo_pixmap)

        # 3. Chromatic Aberration Glitch Title
        font_title = QtGui.QFont("Monospace", 18, QtGui.QFont.Black)
        font_title.setStyleHint(QtGui.QFont.Monospace)
        font_title.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, 4.0)
        title_rect = QtCore.QRectF(0, 90, w, 26)

        if self._glitch_active:
            # Magenta / Red chromatic split
            painter.setFont(font_title)
            painter.setPen(QtGui.QColor(255, 0, 60, 170))
            painter.drawText(title_rect.translated(self._glitch_shift_x - 2, self._glitch_shift_y), QtCore.Qt.AlignCenter, self.title)

            # Cyan chromatic split
            painter.setPen(QtGui.QColor(0, 240, 255, 170))
            painter.drawText(title_rect.translated(self._glitch_shift_x + 2, -self._glitch_shift_y), QtCore.Qt.AlignCenter, self.title)

        # Main Title (Crisp Neon Cyan)
        painter.setFont(font_title)
        painter.setPen(QtGui.QColor("#00f0ff"))
        painter.drawText(title_rect, QtCore.Qt.AlignCenter, self.title)

        # Subtitle
        font_sub = QtGui.QFont("Monospace", 9, QtGui.QFont.Bold)
        font_sub.setStyleHint(QtGui.QFont.Monospace)
        font_sub.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, 2.0)
        painter.setFont(font_sub)
        painter.setPen(QtGui.QColor("#4a7880"))
        sub_rect = QtCore.QRectF(0, 118, w, 16)
        painter.drawText(sub_rect, QtCore.Qt.AlignCenter, f"// {self.subtitle} //")


class CyberpunkSplashWidget(QtWidgets.QWidget):
    """Cyberpunk 2077 HUD splash canvas with CRT scanlines, HUD corner brackets, and digital glitch artifacts."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._glitch_blocks: list[tuple[int, int, int, int, str]] = []
        self._scanline_phase = 0.0

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(60)  # ~16 FPS
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    def _on_tick(self) -> None:
        self._scanline_phase = (self._scanline_phase + 0.5) % 4.0

        # Localized micro digital glitch blocks
        if random.random() < 0.22:
            num_blocks = random.randint(1, 3)
            self._glitch_blocks = []
            hex_samples = ["7A", "1C", "E9", "55", "BD", "FF", "00"]
            for _ in range(num_blocks):
                bx = random.randint(16, max(20, self.width() - 80))
                by = random.randint(16, max(20, self.height() - 40))
                bw = random.randint(28, 56)
                bh = random.randint(8, 12)
                txt = random.choice(hex_samples) + " " + random.choice(hex_samples)
                self._glitch_blocks.append((bx, by, bw, bh, txt))
        else:
            self._glitch_blocks = []

        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        w = self.width()
        h = self.height()

        # 1. Dark Cyberpunk background with subtle edge vignette
        painter.fillRect(0, 0, w, h, QtGui.QColor("#05080c"))

        # Top and bottom neon accent border lines
        painter.setPen(QtGui.QPen(QtGui.QColor("#00f0ff"), 1.8))
        painter.drawLine(0, 0, w, 0)
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 240, 255, 90), 1.0))
        painter.drawLine(0, h - 1, w, h - 1)

        # 2. Subtle CRT scanlines
        pen_scanline = QtGui.QPen(QtGui.QColor(0, 240, 255, 6))
        pen_scanline.setWidth(1)
        painter.setPen(pen_scanline)
        y = int(self._scanline_phase)
        while y < h:
            painter.drawLine(0, y, w, y)
            y += 4

        # 3. Corner HUD brackets with crosshairs and index numbers
        bracket_len = 18
        bracket_margin = 10
        pen_bracket = QtGui.QPen(QtGui.QColor("#00f0ff"), 1.8)
        painter.setPen(pen_bracket)

        # Top-Left [ ┌ ]
        painter.drawLine(bracket_margin, bracket_margin, bracket_margin + bracket_len, bracket_margin)
        painter.drawLine(bracket_margin, bracket_margin, bracket_margin, bracket_margin + bracket_len)

        # Top-Right [ ┐ ]
        painter.drawLine(w - bracket_margin, bracket_margin, w - bracket_margin - bracket_len, bracket_margin)
        painter.drawLine(w - bracket_margin, bracket_margin, w - bracket_margin, bracket_margin + bracket_len)

        # Bottom-Left [ └ ]
        painter.drawLine(bracket_margin, h - bracket_margin, bracket_margin + bracket_len, h - bracket_margin)
        painter.drawLine(bracket_margin, h - bracket_margin, bracket_margin, h - bracket_margin - bracket_len)

        # Bottom-Right [ ┘ ]
        painter.drawLine(w - bracket_margin, h - bracket_margin, w - bracket_margin - bracket_len, h - bracket_margin)
        painter.drawLine(w - bracket_margin, h - bracket_margin, w - bracket_margin, h - bracket_margin - bracket_len)

        # Small corner labels
        painter.setFont(QtGui.QFont("Monospace", 6, QtGui.QFont.Bold))
        painter.setPen(QtGui.QColor(0, 240, 255, 120))
        painter.drawText(bracket_margin + 3, bracket_margin + 12, "01")
        painter.drawText(w - bracket_margin - 14, bracket_margin + 12, "02")
        painter.drawText(bracket_margin + 3, h - bracket_margin - 3, "03")
        painter.drawText(w - bracket_margin - 14, h - bracket_margin - 3, "04")

        # 4. Localized digital noise / glitch blocks
        for bx, by, bw, bh, txt in self._glitch_blocks:
            rect = QtCore.QRectF(bx, by, bw, bh)
            is_yellow = random.random() < 0.5
            color = QtGui.QColor(252, 238, 10, 45) if is_yellow else QtGui.QColor(0, 240, 255, 40)
            painter.fillRect(rect, color)
            painter.setPen(QtGui.QPen(QtGui.QColor("#fcee0a" if is_yellow else "#00f0ff"), 1.0))
            painter.drawRect(rect)
            painter.setFont(QtGui.QFont("Monospace", 6))
            painter.drawText(rect, QtCore.Qt.AlignCenter, txt)


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

        self.window = CyberpunkSplashWidget()
        self.window.setWindowTitle(DESKTOP_APP_NAME)
        self.window.setFixedSize(680, 360)
        self.window.setObjectName("splashRoot")
        self.window.setStyleSheet("QWidget#splashRoot { background: #05080c; color: #00f0ff; }")

        layout = QtWidgets.QVBoxLayout(self.window)
        layout.setContentsMargins(32, 18, 32, 18)
        layout.setSpacing(4)

        # Cyberpunk Top HUD bar
        top_hud = QtWidgets.QHBoxLayout()
        top_hud.setContentsMargins(0, 0, 0, 0)
        hud_left = QtWidgets.QLabel("[ BREACH PROTOCOL // CYBERDECK v2.077 ]")
        hud_left.setStyleSheet(
            "font-family: monospace; font-size: 9px; font-weight: 800; color: #00f0ff; letter-spacing: 1px; background: transparent; border: 0;"
        )
        hud_right = QtWidgets.QLabel("● NET_STATUS: OVERRIDE")
        hud_right.setStyleSheet(
            "font-family: monospace; font-size: 9px; font-weight: 800; color: #fcee0a; letter-spacing: 1px; background: transparent; border: 0;"
        )
        top_hud.addWidget(hud_left)
        top_hud.addStretch(1)
        top_hud.addWidget(hud_right)
        layout.addLayout(top_hud)

        # Center Logo Reticle & Chromatic Glitch Title
        pixmap = load_logo_pixmap(QtGui, 72)
        self.center_widget = GlitchHeaderCenterWidget(
            pixmap, DESKTOP_APP_NAME, DESKTOP_IDENTITY_TEXT.upper(), self.window
        )
        layout.addWidget(self.center_widget)

        layout.addStretch(1)

        # Phase label
        self.phase = QtWidgets.QLabel("")
        self.phase.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.phase.setStyleSheet(
            "font-family: monospace; font-size: 10px; font-weight: 800; color: #fcee0a; letter-spacing: 1px; background: transparent; border: 0;"
        )
        layout.addWidget(self.phase)

        layout.addSpacing(2)

        # Cyberdeck RAM Hack Bar
        self.progress = CyberdeckRamBar(self.window, total_units=16)
        self.progress.setRange(0, len(BOOT_PHASES))
        layout.addWidget(self.progress)

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

        if self.index < len(PHASE_CYBER_MESSAGES):
            self.phase.setText(PHASE_CYBER_MESSAGES[self.index])
        else:
            self.phase.setText(f"[>] {BOOT_PHASES[self.index]} // READY")

        self.progress.setValue(self.index + 1)
        self.QtCore.QTimer.singleShot(phase_delay_ms(), self._advance)
