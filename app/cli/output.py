from __future__ import annotations

import json
import os
import sys
from typing import Any, Iterable, Mapping, Sequence

from app.cli.config_view import is_secret_key


_COLORS = {
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}


def redact_data(value: Any, key: str = "") -> Any:
    if key and is_secret_key(key):
        return "********" if value not in {None, ""} else value
    if isinstance(value, dict):
        return {str(k): redact_data(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_data(item) for item in value]
    if isinstance(value, tuple):
        return [redact_data(item) for item in value]
    return value


def emit_json(value: Any, *, stream=None) -> None:
    stream = stream or sys.stdout
    print(json.dumps(redact_data(value), ensure_ascii=False, indent=2, sort_keys=True), file=stream)


def color_enabled(no_color: bool = False, stream=None) -> bool:
    stream = stream or sys.stdout
    return not no_color and "NO_COLOR" not in os.environ and bool(getattr(stream, "isatty", lambda: False)())


def colorize(text: str, color: str, *, no_color: bool = False, stream=None) -> str:
    if not color_enabled(no_color, stream):
        return text
    return f"{_COLORS[color]}{text}{_COLORS['reset']}"


def prefix(kind: str, *, no_color: bool = False, stream=None) -> str:
    mapping = {
        "success": ("[+]", "green"),
        "info": ("[i]", "cyan"),
        "warn": ("[!]", "yellow"),
        "error": ("[-]", "red"),
    }
    marker, color = mapping[kind]
    return colorize(marker, color, no_color=no_color, stream=stream)


def message(text: str, *, kind: str = "info", no_color: bool = False, stream=None) -> None:
    stream = stream or (sys.stderr if kind in {"warn", "error"} else sys.stdout)
    print(f"{prefix(kind, no_color=no_color, stream=stream)} {text}", file=stream)


def key_values(rows: Iterable[tuple[str, Any]], *, stream=None) -> None:
    stream = stream or sys.stdout
    prepared = [(str(key), "" if value is None else str(value)) for key, value in rows]
    width = max((len(key) for key, _ in prepared), default=0)
    for key, value in prepared:
        print(f"{key:<{width}}  {value}", file=stream)


def table(headers: Sequence[str], rows: Sequence[Sequence[Any]], *, stream=None) -> None:
    stream = stream or sys.stdout
    text_rows = [["" if value is None else str(value) for value in row] for row in rows]
    widths = [len(str(header)) for header in headers]
    for row in text_rows:
        for index, value in enumerate(row):
            if index < len(widths):
                widths[index] = max(widths[index], len(value))
    print("  ".join(str(header).ljust(widths[index]) for index, header in enumerate(headers)), file=stream)
    print("  ".join("-" * width for width in widths), file=stream)
    for row in text_rows:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)), file=stream)


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
    stream = stream or sys.stdout
    for check in checks:
        status = str(check.get("status", "unknown")).upper()
        print(f"{status:<5} {check.get('name', ''):<24} {check.get('message', '')}", file=stream)
