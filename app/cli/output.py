from __future__ import annotations

import json
import os
import re
import shutil
import sys
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence, TextIO

from app.cli.config_view import is_secret_key


BRAND_NAME = "BotQuangAnh"
BRAND_SYMBOL = "◆"
INDENT = 2
CONTINUATION_INDENT = 4
SECTION_GAP = 1
LABEL_GAP = 3
COMPACT_WIDTH = 70
WIDE_WIDTH = 100

_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_OSC_RE = re.compile(r"\x1b\][^\x07]*(?:\x07|\x1b\\)")
_COLORS = {
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}
_STATUS = {
    "healthy": ("●", "green"),
    "running": ("●", "green"),
    "ready": ("●", "green"),
    "pass": ("●", "green"),
    "success": ("●", "green"),
    "allowed": ("●", "green"),
    "degraded": ("▲", "yellow"),
    "warning": ("▲", "yellow"),
    "warn": ("▲", "yellow"),
    "starting": ("▲", "yellow"),
    "failed": ("×", "red"),
    "fail": ("×", "red"),
    "error": ("×", "red"),
    "unhealthy": ("×", "red"),
    "blocked": ("×", "red"),
    "offline": ("○", "dim"),
    "stopped": ("○", "dim"),
    "unknown": ("○", "dim"),
}


class OutputMode(str, Enum):
    HUMAN = "human"
    QUIET = "quiet"
    JSON = "json"


def redact_data(value: Any, key: str = "") -> Any:
    if key and is_secret_key(key):
        return "<redacted>" if value not in {None, ""} else value
    if isinstance(value, dict):
        return {str(k): redact_data(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_data(item) for item in value]
    if isinstance(value, tuple):
        return [redact_data(item) for item in value]
    return value


def emit_json(value: Any, *, stream: TextIO | None = None) -> None:
    target = stream or sys.stdout
    print(
        json.dumps(redact_data(value), ensure_ascii=False, indent=2, sort_keys=True),
        file=target,
    )


def emit_quiet(value: Any, *, stream: TextIO | None = None) -> None:
    target = stream or sys.stdout
    if value is None:
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            print(strip_ansi(str(item)), file=target)
        return
    print(strip_ansi(str(value)), file=target)


def strip_ansi(value: str) -> str:
    return _CSI_RE.sub("", _OSC_RE.sub("", str(value)))


def _cell_width(char: str) -> int:
    if char in {"\n", "\r"}:
        return 0
    if unicodedata.combining(char):
        return 0
    category = unicodedata.category(char)
    if category.startswith("C") and char != "\t":
        return 0
    if char == "\t":
        return 4
    return 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1


def visible_width(value: str) -> int:
    return sum(_cell_width(char) for char in strip_ansi(value))


def truncate_visible(value: str, max_width: int, ellipsis: str = "…") -> str:
    if max_width <= 0:
        return ""
    if visible_width(value) <= max_width:
        return value
    ellipsis_width = visible_width(ellipsis)
    if ellipsis_width >= max_width:
        return ellipsis if ellipsis_width == max_width else ""
    target = max_width - ellipsis_width
    result: list[str] = []
    width = 0
    for char in strip_ansi(value):
        char_width = _cell_width(char)
        if width + char_width > target:
            break
        result.append(char)
        width += char_width
    return "".join(result) + ellipsis


def pad_to_width(value: str, target_width: int, *, align: str = "left") -> str:
    clean_width = visible_width(value)
    padding = max(0, target_width - clean_width)
    if align == "right":
        return " " * padding + value
    return value + " " * padding


def wrap_visible(value: str, max_width: int) -> list[str]:
    text = strip_ansi(str(value)).strip()
    if not text:
        return [""]
    if max_width <= 1:
        return [truncate_visible(text, max_width)]
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            if visible_width(word) > max_width:
                if current:
                    lines.append(current)
                    current = ""
                remaining = word
                while visible_width(remaining) > max_width:
                    chunk = truncate_visible(remaining, max_width, ellipsis="")
                    if not chunk:
                        break
                    lines.append(chunk)
                    remaining = remaining[len(chunk) :]
                current = remaining
                continue
            candidate = word if not current else f"{current} {word}"
            if visible_width(candidate) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines or [""]


def terminal_width(stream: TextIO | None = None, fallback: int = 100) -> int:
    stream = stream or sys.stdout
    try:
        return max(40, shutil.get_terminal_size(fallback=(fallback, 24)).columns)
    except OSError:
        return fallback


def color_enabled(color_mode: str = "auto", stream: TextIO | None = None) -> bool:
    stream = stream or sys.stdout
    if color_mode == "never":
        return False
    if color_mode == "always":
        return True
    if "NO_COLOR" in os.environ or os.getenv("TERM", "") == "dumb" or os.getenv("CI"):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def style(
    text: str,
    role: str,
    *,
    color_mode: str = "auto",
    stream: TextIO | None = None,
) -> str:
    if not color_enabled(color_mode, stream):
        return text
    return f"{_COLORS[role]}{text}{_COLORS['reset']}"


def external_text(value: str, *, color_mode: str = "auto") -> str:
    return strip_ansi(value) if color_mode == "never" else value


@dataclass(slots=True)
class Renderer:
    color_mode: str = "auto"
    stream: TextIO = sys.stdout
    width: int | None = None

    @property
    def columns(self) -> int:
        return self.width or terminal_width(self.stream)

    def _write(self, line: str = "") -> None:
        print(line.rstrip(), file=self.stream)

    def header(self, context: str, subtitle: str | None = None) -> None:
        brand = style(
            f"{BRAND_SYMBOL} {BRAND_NAME}",
            "cyan",
            color_mode=self.color_mode,
            stream=self.stream,
        )
        self._write(brand)
        detail = context if not subtitle else f"{context} · {subtitle}"
        for index, line in enumerate(
            wrap_visible(detail, max(10, self.columns - INDENT))
        ):
            prefix = " " * INDENT if index == 0 else " " * CONTINUATION_INDENT
            self._write(
                prefix
                + style(
                    line,
                    "dim",
                    color_mode=self.color_mode,
                    stream=self.stream,
                )
            )

    def blank(self) -> None:
        self._write()

    def status(self, state: str, text: str | None = None) -> None:
        normalized = state.lower().strip() or "unknown"
        symbol, color = _STATUS.get(normalized, _STATUS["unknown"])
        label = text or normalized
        marker = style(symbol, color, color_mode=self.color_mode, stream=self.stream)
        self._write(f"{' ' * INDENT}{marker} {label}")

    def section(self, title: str) -> None:
        self._write(
            " " * INDENT
            + style(title, "bold", color_mode=self.color_mode, stream=self.stream)
        )

    def facts(self, rows: Iterable[tuple[str, Any]]) -> None:
        prepared = [
            (str(key), "" if value is None else str(value)) for key, value in rows
        ]
        if not prepared:
            return
        if self.columns < COMPACT_WIDTH:
            value_width = max(10, self.columns - CONTINUATION_INDENT)
            for key, value in prepared:
                self._write(
                    " " * INDENT
                    + style(key, "dim", color_mode=self.color_mode, stream=self.stream)
                )
                for line in wrap_visible(value, value_width):
                    self._write(" " * CONTINUATION_INDENT + line)
            return

        label_width = max(visible_width(key) for key, _ in prepared)
        label_width = min(label_width, max(12, self.columns // 3))
        value_width = max(10, self.columns - INDENT - label_width - LABEL_GAP)
        for key, value in prepared:
            lines = wrap_visible(value, value_width)
            rendered_key = style(
                pad_to_width(truncate_visible(key, label_width), label_width),
                "dim",
                color_mode=self.color_mode,
                stream=self.stream,
            )
            self._write(" " * INDENT + rendered_key + " " * LABEL_GAP + lines[0])
            continuation = " " * (INDENT + label_width + LABEL_GAP)
            for line in lines[1:]:
                self._write(continuation + line)

    def table(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[Any]],
        *,
        numeric_columns: Iterable[int] = (),
    ) -> None:
        text_rows = [
            ["" if value is None else str(value) for value in row] for row in rows
        ]
        header_values = [str(header) for header in headers]
        if not header_values:
            return
        if self.columns < COMPACT_WIDTH:
            for row_index, row in enumerate(text_rows):
                if row_index:
                    self.blank()
                self.facts(
                    [
                        (header_values[index], row[index] if index < len(row) else "")
                        for index in range(len(header_values))
                    ]
                )
            return

        column_count = len(header_values)
        widths = [visible_width(header) for header in header_values]
        for row in text_rows:
            for index in range(column_count):
                value = row[index] if index < len(row) else ""
                widths[index] = max(widths[index], visible_width(value))

        available = max(column_count, self.columns - INDENT - 2 * (column_count - 1))
        minimums = [
            min(widths[index], max(4, visible_width(header_values[index])))
            for index in range(column_count)
        ]
        while sum(widths) > available:
            candidates = [
                index
                for index in range(column_count)
                if widths[index] > minimums[index]
            ]
            if not candidates:
                break
            widest = max(candidates, key=lambda index: widths[index] - minimums[index])
            widths[widest] -= 1

        numeric = set(numeric_columns)
        header_line = "  ".join(
            pad_to_width(
                truncate_visible(header_values[index], widths[index]),
                widths[index],
                align="right" if index in numeric else "left",
            )
            for index in range(column_count)
        )
        self._write(
            " " * INDENT
            + style(
                header_line.rstrip(),
                "dim",
                color_mode=self.color_mode,
                stream=self.stream,
            )
        )
        for row in text_rows:
            cells = []
            for index in range(column_count):
                value = row[index] if index < len(row) else ""
                cells.append(
                    pad_to_width(
                        truncate_visible(value, widths[index]),
                        widths[index],
                        align="right" if index in numeric else "left",
                    )
                )
            self._write(" " * INDENT + "  ".join(cells).rstrip())

    def checks(self, checks: Sequence[Mapping[str, Any]]) -> None:
        rows: list[list[str]] = []
        for check in checks:
            status = str(check.get("status", "unknown")).lower()
            symbol, color = _STATUS.get(status, _STATUS["unknown"])
            marker = style(
                symbol,
                color,
                color_mode=self.color_mode,
                stream=self.stream,
            )
            rows.append(
                [
                    f"{marker} {status}",
                    str(check.get("name", "")),
                    str(check.get("message", "")),
                ]
            )
        self.table(["STATE", "CHECK", "DETAIL"], rows)

    def summary(self, text: str, state: str | None = None) -> None:
        if state:
            self.status(state, text)
        else:
            self._write(" " * INDENT + text)

    def hint(self, command: str, intro: str = "Run") -> None:
        prefix = " " * INDENT + "› "
        available = max(10, self.columns - visible_width(prefix))
        single_line = f"{intro} `{command}`"
        if visible_width(single_line) <= available:
            self._write(
                prefix
                + style(
                    single_line,
                    "dim",
                    color_mode=self.color_mode,
                    stream=self.stream,
                )
            )
            return

        heading = f"{intro.rstrip(':')}:"
        self._write(
            prefix
            + style(
                heading,
                "dim",
                color_mode=self.color_mode,
                stream=self.stream,
            )
        )
        command_width = max(10, self.columns - CONTINUATION_INDENT)
        for line in wrap_visible(command, command_width):
            self._write(
                " " * CONTINUATION_INDENT
                + style(
                    line,
                    "dim",
                    color_mode=self.color_mode,
                    stream=self.stream,
                )
            )

    def warning(self, text: str) -> None:
        self.status("warn", text)

    def error(
        self, title: str, reason: str | None = None, hint: str | None = None
    ) -> None:
        self.header("Operation failed")
        self.blank()
        self.status("error", title)
        if reason and reason != title:
            self.blank()
            for line in wrap_visible(reason, max(10, self.columns - INDENT)):
                self._write(" " * INDENT + line)
        if hint:
            self.blank()
            self._write(" " * INDENT + "Try:")
            self._write(" " * CONTINUATION_INDENT + hint)


def renderer_for(
    ctx: Any, *, stream: TextIO | None = None, width: int | None = None
) -> Renderer:
    return Renderer(
        color_mode=getattr(
            ctx, "color", "never" if getattr(ctx, "no_color", False) else "auto"
        ),
        stream=stream or sys.stdout,
        width=width,
    )


# Compatibility helpers used by raw-data commands and older extensions.
def colorize(text: str, color: str, *, no_color: bool = False, stream=None) -> str:
    return style(text, color, color_mode="never" if no_color else "auto", stream=stream)


def message(
    text: str, *, kind: str = "info", no_color: bool = False, stream=None
) -> None:
    target = stream or (sys.stderr if kind in {"warn", "error"} else sys.stdout)
    state = {
        "info": "unknown",
        "success": "success",
        "warn": "warn",
        "error": "error",
    }.get(kind, kind)
    Renderer(color_mode="never" if no_color else "auto", stream=target).status(
        state, text
    )


def key_values(rows: Iterable[tuple[str, Any]], *, stream=None) -> None:
    Renderer(stream=stream or sys.stdout).facts(rows)


def table(
    headers: Sequence[str], rows: Sequence[Sequence[Any]], *, stream=None
) -> None:
    Renderer(stream=stream or sys.stdout).table(headers, rows)


def human_duration(seconds: float | int) -> str:
    total = max(0, int(float(seconds)))
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def render_checks(checks: Sequence[Mapping[str, Any]], *, stream=None) -> None:
    Renderer(stream=stream or sys.stdout).checks(checks)
