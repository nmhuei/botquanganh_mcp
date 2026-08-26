from __future__ import annotations

import os
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, TextIO

from app.cli.output import OutputMode, style, terminal_width, truncate_visible

# Values copied from uv's current PrepareReporter/ProgressReporter UI contract.
_SPINNER = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
_TICK_SECONDS = 0.20
_RENDER_DELAY_SECONDS = 0.0
_REQUEST_BAR_WIDTH = 30


def _is_tty(stream: TextIO) -> bool:
    return bool(getattr(stream, "isatty", lambda: False)())


def _format_elapsed(seconds: float) -> str:
    if seconds < 1:
        return f"{max(0, round(seconds * 1000))}ms"
    if seconds < 60:
        rendered = f"{seconds:.2f}".rstrip("0").rstrip(".")
        return f"{rendered}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {seconds:04.1f}s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(minutes)}m"


def _binary_bytes(value: int) -> str:
    value = max(0, int(value))
    for divisor, suffix in ((1024**3, "GiB"), (1024**2, "MiB"), (1024, "KiB")):
        if value >= divisor:
            return f"{value / divisor:.2f} {suffix}"
    return f"{value} B"


@dataclass(slots=True)
class ProgressRow:
    name: str
    current: int = 0
    total: int | None = 1
    binary_bytes: bool = False


@dataclass(slots=True)
class ProgressReporter:
    """uv PrepareReporter-style root spinner plus transient child rows."""

    color_mode: str = "auto"
    output_mode: OutputMode = OutputMode.HUMAN
    no_progress: bool = False
    verbose: bool = False
    summary_non_tty: bool = True
    message: str = "Working..."
    total: int | None = None
    stream: TextIO = sys.stderr
    render_delay: float = _RENDER_DELAY_SECONDS
    _completed: int = 0
    _started_at: float = field(default_factory=time.monotonic)
    _frame: int = 0
    _closed: bool = False
    _drawn_lines: int = 0
    _last_lines: list[str] = field(default_factory=list)
    _stop: threading.Event = field(default_factory=threading.Event)
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _thread: threading.Thread | None = None
    _rows: OrderedDict[str, ProgressRow] = field(default_factory=OrderedDict)

    @property
    def human(self) -> bool:
        return self.output_mode is OutputMode.HUMAN

    @property
    def animated(self) -> bool:
        if not self.human or self.no_progress or self.verbose:
            return False
        if os.getenv("BQA_NO_PROGRESS", "").strip().lower() in {"1", "true", "yes", "on"}:
            return False
        # Suppressed color implies suppressed motion: the visual contract
        # forbids ANY escape bytes (cursor movement included) when styling is
        # off, so NO_COLOR (any non-empty value, per spec) and the explicit
        # "none" mode both disable the live block entirely.
        if os.getenv("NO_COLOR", "") != "":
            return False
        if self.color_mode == "none":
            return False
        if os.getenv("TERM", "") == "dumb":
            return False
        return _is_tty(self.stream)

    @property
    def style_mode(self) -> str:
        """Color mode handed to style(): "none" maps to full suppression.

        style()/color_enabled() only knows "never"; leaving "none" unchecked
        would fall through to the isatty branch and emit SGR codes on a tty.
        """
        return "never" if self.color_mode == "none" else self.color_mode

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, time.monotonic() - self._started_at)

    def __enter__(self) -> "ProgressReporter":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        if not self._closed:
            self.close(clear=True)
        return False

    def start(self) -> None:
        if self._thread is not None or not self.animated:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(_TICK_SECONDS):
            if self.elapsed_seconds < self.render_delay:
                continue
            self._render()
            self._frame = (self._frame + 1) % len(_SPINNER)

    def _root_line(self) -> str:
        spinner = style(_SPINNER[self._frame], "white", color_mode=self.style_mode, stream=self.stream)
        message = style(self.message, "dim", color_mode=self.style_mode, stream=self.stream)
        suffix = ""
        if self.total is not None:
            total = max(0, int(self.total))
            completed = min(max(0, self._completed), total)
            suffix = f" ({completed}/{total})"
        elapsed = ""
        if self.elapsed_seconds >= 2.0:
            rendered = _format_elapsed(self.elapsed_seconds)
            elapsed = " · " + style(rendered, "dim", color_mode=self.style_mode, stream=self.stream)
        return f"{spinner} {message}{suffix}{elapsed}"

    def _row_lines(self) -> list[str]:
        if not self._rows:
            return []
        max_name = max(len(row.name) for row in self._rows.values())
        lines: list[str] = []
        for row in self._rows.values():
            name = style(row.name.ljust(max_name), "dim", color_mode=self.style_mode, stream=self.stream)
            if row.total is None:
                lines.append(f"{name} ....")
                continue
            total = max(1, int(row.total))
            current = min(max(0, int(row.current)), total)
            filled = round(_REQUEST_BAR_WIDTH * (current / total))
            done = style("-" * filled, "green", color_mode=self.style_mode, stream=self.stream)
            left = style("-" * (_REQUEST_BAR_WIDTH - filled), "black_dim", color_mode=self.style_mode, stream=self.stream)
            # The metric is this row's final plain-text tail segment; strip its
            # padding here so no row line ends with invisible trailing spaces
            # (rstrip must never touch a styled segment, only plain text).
            if row.binary_bytes:
                metric = f"{_binary_bytes(current):>7}/{_binary_bytes(total):7}".rstrip()
            else:
                metric = f"{current:>3}/{total:<3}".rstrip()
            lines.append(f"{name} {done}{left} {metric}")
        return lines

    def _lines(self) -> list[str]:
        width = max(20, terminal_width(self.stream) - 1)
        return [truncate_visible(line, width) for line in [self._root_line(), *self._row_lines()]]

    def _erase_previous(self) -> None:
        count = self._drawn_lines
        if count <= 0:
            return
        self.stream.write("\r")
        if count > 1:
            self.stream.write(f"\x1b[{count - 1}A")
        for index in range(count):
            self.stream.write("\x1b[2K")
            if index < count - 1:
                self.stream.write("\x1b[1B\r")
        if count > 1:
            self.stream.write(f"\x1b[{count - 1}A")
        self.stream.write("\r")
        self._drawn_lines = 0

    def _render(self) -> None:
        if not self.animated or self._closed:
            return
        with self._lock:
            previous = self._last_lines
            lines = self._lines()
            if previous and len(previous) == len(lines):
                # Same block shape: update only rows whose content changed.
                stream = self.stream
                stream.write("\r")
                if len(lines) > 1:
                    stream.write(f"\x1b[{len(lines) - 1}A")
                for index, (line, prev) in enumerate(zip(lines, previous)):
                    if line != prev:
                        stream.write(f"\x1b[2K{line}")
                    if index < len(lines) - 1:
                        stream.write("\r\x1b[1B")
                stream.flush()
                self._last_lines = lines
                return
            if previous:
                self._erase_previous()
            self.stream.write("\n".join(lines))
            self.stream.flush()
            self._drawn_lines = len(lines)
            self._last_lines = lines

    def set_items(self, names: list[str] | tuple[str, ...], *, total_each: int | None = 1) -> None:
        with self._lock:
            self._rows = OrderedDict((str(name), ProgressRow(str(name), 0, total_each)) for name in names)
        if self.animated and self.elapsed_seconds >= self.render_delay:
            self._render()

    def start_item(self, name: str, *, total: int | None = 1, current: int = 0, binary_bytes: bool = False) -> None:
        with self._lock:
            self._rows[str(name)] = ProgressRow(str(name), int(current), None if total is None else int(total), binary_bytes)
        if self.animated and self.elapsed_seconds >= self.render_delay:
            self._render()

    def update_item(self, name: str, current: int, *, total: int | None = None) -> None:
        with self._lock:
            row = self._rows.get(str(name))
            if row is None:
                self._rows[str(name)] = ProgressRow(str(name), int(current), total)
            else:
                row.current = int(current)
                if total is not None:
                    row.total = int(total)
        if self.animated and self.elapsed_seconds >= self.render_delay:
            self._render()

    def complete_item(self, name: str, *, advance_root: bool = True) -> None:
        with self._lock:
            self._rows.pop(str(name), None)
            if advance_root:
                self._completed += 1
                if self.total is not None:
                    self._completed = min(self._completed, max(0, int(self.total)))
        if self.animated and self.elapsed_seconds >= self.render_delay:
            self._render()

    def update(self, message: str, *, completed: int | None = None) -> None:
        with self._lock:
            self.message = str(message)
            if completed is not None:
                self._completed = max(0, int(completed))
        if self.animated and self.elapsed_seconds >= self.render_delay:
            self._render()

    def advance(self, message: str | None = None, *, steps: int = 1) -> None:
        with self._lock:
            self._completed = max(0, self._completed + int(steps))
            if self.total is not None:
                self._completed = min(self._completed, max(0, int(self.total)))
            if message is not None:
                self.message = str(message)
        if self.animated and self.elapsed_seconds >= self.render_delay:
            self._render()

    def finish(self, summary: str, *, detail: str | None = None) -> None:
        if self._closed:
            return
        with self._lock:
            if self.total is not None:
                self._completed = max(0, int(self.total))
            self._rows.clear()
        # No final frame: the transient block is erased by close() right after,
        # so rendering here only causes a visible double-draw artifact.
        self.close(clear=True)
        if not self.human:
            return
        if not self.summary_non_tty and not _is_tty(self.stream):
            return
        elapsed = _format_elapsed(self.elapsed_seconds)
        verb, _, subject = summary.partition(" ")
        rendered_verb = style(verb, "green", color_mode=self.style_mode, stream=self.stream)
        line = rendered_verb
        if subject:
            line += " " + style(subject, "bold", color_mode=self.style_mode, stream=self.stream)
        line += " " + style(f"in {elapsed}", "green", color_mode=self.style_mode, stream=self.stream)
        if detail:
            line += " " + style(detail, "bold", color_mode=self.style_mode, stream=self.stream)
        print(line, file=self.stream)

    def close(self, *, clear: bool = True) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=0.5)
        if clear:
            with self._lock:
                self._erase_previous()
                self._last_lines = []
                self.stream.flush()


def progress_for(ctx: Any, message: str, *, total: int | None = None, stream: TextIO | None = None, summary_non_tty: bool = True) -> ProgressReporter:
    # Mirror renderer_for(): an explicit --no-color / --color never request
    # (ctx.no_color is True exactly when ctx.color == "never") becomes the
    # reporter's fully-suppressed "none" mode so animation dies with styling.
    color = str(getattr(ctx, "color", "auto"))
    if bool(getattr(ctx, "no_color", False)):
        color = "none"
    return ProgressReporter(
        color_mode=color,
        output_mode=getattr(ctx, "output_mode", OutputMode.HUMAN),
        no_progress=bool(getattr(ctx, "no_progress", False)),
        verbose=bool(getattr(ctx, "verbose", False)),
        summary_non_tty=summary_non_tty,
        message=message,
        total=total,
        stream=stream or sys.stderr,
    )
