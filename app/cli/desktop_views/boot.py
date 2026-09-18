"""Short, non-blocking startup sequence for the native desktop UI."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


BOOT_PHASES = (
    "INITIALIZING INTERFACE",
    "LOADING WORKSPACES",
    "CONNECTING ACTIVITY STREAM",
    "READY",
)
BOOT_PHASE_INTERVAL_MS = 750
BOOT_READY_DELAY_MS = 750
BOOT_WIDTH = 680
BOOT_HEIGHT = 360


class BootSequence:
    """Schedule ordered boot phases without blocking Tk's event loop."""

    def __init__(
        self,
        schedule: Callable[[int, Callable[[], None]], Any],
        cancel_scheduled: Callable[[Any], None],
        on_phase: Callable[[str], None],
        on_ready: Callable[[], None],
    ) -> None:
        self.schedule = schedule
        self.cancel_scheduled = cancel_scheduled
        self.on_phase = on_phase
        self.on_ready = on_ready
        self.phase_index = -1
        self.job: Any = None
        self.active = False

    def start(self) -> None:
        if self.active:
            return
        self.active = True
        self._advance()

    def cancel(self) -> None:
        self.active = False
        if self.job is not None:
            self.cancel_scheduled(self.job)
            self.job = None

    def _advance(self) -> None:
        if not self.active:
            return
        self.job = None
        self.phase_index += 1
        self.on_phase(BOOT_PHASES[self.phase_index])
        if self.phase_index == len(BOOT_PHASES) - 1:
            self.job = self.schedule(BOOT_READY_DELAY_MS, self._complete)
            return
        self.job = self.schedule(BOOT_PHASE_INTERVAL_MS, self._advance)

    def _complete(self) -> None:
        self.job = None
        if not self.active:
            return
        self.active = False
        self.on_ready()


class DesktopBootScreen:
    """A small procedural splash screen that hands control to the dashboard."""

    def __init__(self, root: Any, tk: Any, *, on_ready: Callable[[], None]) -> None:
        self.root = root
        self.tk = tk
        self.on_ready = on_ready
        self.closed = False
        self.window = tk.Toplevel(root)
        self.window.configure(background="#070b0b")
        self.window.overrideredirect(True)
        self.window.resizable(False, False)
        left = max(0, (self.window.winfo_screenwidth() - BOOT_WIDTH) // 2)
        top = max(0, (self.window.winfo_screenheight() - BOOT_HEIGHT) // 2)
        self.window.geometry(f"{BOOT_WIDTH}x{BOOT_HEIGHT}+{left}+{top}")
        self.canvas = tk.Canvas(
            self.window,
            width=BOOT_WIDTH,
            height=BOOT_HEIGHT,
            background="#070b0b",
            highlightthickness=0,
            borderwidth=0,
        )
        self.canvas.pack(fill="both", expand=True)
        self._draw_shell()
        self.sequence = BootSequence(
            root.after,
            root.after_cancel,
            self._show_phase,
            self._finish,
        )

    def _draw_shell(self) -> None:
        self.canvas.create_rectangle(
            18,
            18,
            BOOT_WIDTH - 18,
            BOOT_HEIGHT - 18,
            outline="#1f6f4a",
            width=1,
        )
        for y in range(42, BOOT_HEIGHT - 40, 24):
            self.canvas.create_line(34, y, BOOT_WIDTH - 34, y, fill="#0c2019")
        self.canvas.create_text(
            BOOT_WIDTH // 2,
            102,
            text="U C S",
            fill="#a3ff12",
            font=("TkFixedFont", 34, "bold"),
        )
        self.canvas.create_text(
            BOOT_WIDTH // 2,
            142,
            text="SECRETAGENT // SECURE DESKTOP",
            fill="#77b995",
            font=("TkFixedFont", 11, "bold"),
        )
        self.canvas.create_line(202, 168, 478, 168, fill="#2dd4bf")
        self.phase_item = self.canvas.create_text(
            BOOT_WIDTH // 2,
            216,
            text="",
            fill="#e5edf7",
            font=("TkFixedFont", 13, "bold"),
        )
        self.canvas.create_text(
            BOOT_WIDTH // 2,
            246,
            text="SYSTEM BOOTSTRAP // DO NOT INTERRUPT",
            fill="#638075",
            font=("TkFixedFont", 9),
        )
        self.progress_items = []
        start = 250
        for index in range(len(BOOT_PHASES)):
            left = start + (index * 48)
            self.progress_items.append(
                self.canvas.create_rectangle(
                    left,
                    284,
                    left + 34,
                    291,
                    outline="#285240",
                    fill="#12261e",
                )
            )

    def _show_phase(self, phase: str) -> None:
        phase_index = BOOT_PHASES.index(phase)
        self.canvas.itemconfigure(self.phase_item, text=f"> {phase}")
        for index, item in enumerate(self.progress_items):
            fill = "#a3ff12" if index <= phase_index else "#12261e"
            self.canvas.itemconfigure(item, fill=fill)

    def start(self) -> None:
        self.sequence.start()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.sequence.cancel()
        self.window.destroy()

    def _finish(self) -> None:
        self.close()
        self.on_ready()
