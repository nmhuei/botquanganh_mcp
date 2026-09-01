#!/usr/bin/env python3
"""Capture and audit the QML BQA Center without mutating server/tunnel state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import time

from PySide6.QtCore import QObject
from PySide6.QtGui import QGuiApplication

from app.cli.center.persistence import CenterWindowStateStore
from app.cli.config_view import load_env
from app.cli.context import CLIContext
from app.cli.lifecycle import status_data
from app.cli.ui_preferences import UIPreferencesStore
from app.qml_ui.app import create_qml_runtime, mark_qt_shutting_down


DEFAULT_SIZES = ("960x650", "1180x760", "1366x768", "1600x900")


def _ctx(repo_root: Path) -> CLIContext:
    values = load_env(repo_root)
    port = str(values.get("MCP_PORT", "18427") or "18427")
    host = str(values.get("MCP_CONNECT_HOST", "127.0.0.1") or "127.0.0.1")
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    return CLIContext(
        repo_root=repo_root,
        values=values,
        base_url=f"http://{host}:{port}",
        token=str(values.get("GATEWAY_TOKEN") or ""),
        request_timeout=2.0,
    )


def _settle(app: QGuiApplication, milliseconds: int = 140) -> None:
    deadline = time.monotonic() + milliseconds / 1000.0
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


def _text_issues(root: QObject) -> list[str]:
    issues: list[str] = []
    for obj in root.findChildren(QObject):
        class_name = obj.metaObject().className()
        if "Text" not in class_name:
            continue
        try:
            visible = bool(obj.property("visible"))
            text = str(obj.property("text") or "")
            width = float(obj.property("width") or 0)
            height = float(obj.property("height") or 0)
            implicit_width = float(obj.property("implicitWidth") or 0)
            implicit_height = float(obj.property("implicitHeight") or 0)
            elide = int(obj.property("elide") or 0)
            wrap_mode = int(obj.property("wrapMode") or 0)
        except Exception:
            continue
        if not visible or not text or width <= 1 or height <= 1:
            continue
        # Elided and wrapped text is intentionally constrained.
        if elide == 0 and wrap_mode == 0 and implicit_width > width + 3:
            issues.append(
                f"text-width:{class_name}:{text[:60]!r}:{implicit_width:.1f}>{width:.1f}"
            )
        if wrap_mode != 0 and implicit_height > height + 3:
            issues.append(
                f"text-height:{class_name}:{text[:60]!r}:{implicit_height:.1f}>{height:.1f}"
            )
    return issues


def _parse_size(value: str) -> tuple[int, int]:
    left, right = value.lower().split("x", 1)
    return int(left), int(right)


def _runtime_fingerprint(ctx: CLIContext) -> dict[str, object]:
    snapshot = status_data(Path(ctx.repo_root), dict(ctx.values))
    return {
        "supervisor": {
            "running": bool((snapshot.get("supervisor") or {}).get("running")),
            "pid": (snapshot.get("supervisor") or {}).get("pid"),
        },
        "server": {
            "running": bool((snapshot.get("server") or {}).get("running")),
            "pid": (snapshot.get("server") or {}).get("pid"),
        },
        "tunnel": {
            "running": bool((snapshot.get("tunnel") or {}).get("running")),
            "pid": (snapshot.get("tunnel") or {}).get("pid"),
        },
        "url": snapshot.get("url"),
        "url_state": snapshot.get("url_state"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-readonly", action="store_true")
    parser.add_argument(
        "--screenshots-dir",
        type=Path,
        default=Path.home() / "Downloads" / "bqa-qml-verification",
    )
    parser.add_argument("--sizes", default=",".join(DEFAULT_SIZES))
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    ctx = _ctx(repo_root)
    runtime_before = _runtime_fingerprint(ctx) if args.live_readonly else None
    verification_state = tempfile.TemporaryDirectory(prefix="bqa-qml-verify-")
    verification_root = Path(verification_state.name)
    app, engine, backend = create_qml_runtime(
        ctx,
        fixture=not args.live_readonly,
        safe_actions=True,
        preferences_store=UIPreferencesStore(verification_root / "ui.json"),
        window_state_store=CenterWindowStateStore(
            verification_root / "window.json"
        ),
    )
    window = engine.rootObjects()[0]
    args.screenshots_dir.mkdir(parents=True, exist_ok=True)
    _settle(app, 700 if args.live_readonly else 180)

    sizes = [_parse_size(item.strip()) for item in args.sizes.split(",") if item.strip()]
    issues: dict[str, list[str]] = {}
    captures: list[str] = []

    views = (
        ("overview", "overview", None),
        ("activity", "activity", None),
        ("workspaces", "workspaces", None),
        ("logs-events", "logs", "events"),
        ("logs-runtime", "logs", "runtime"),
        ("diagnostics", "diagnostics", None),
        ("settings", "settings", None),
    )

    for language in ("en", "vi"):
        backend.changeLanguage(language)
        for view_name, page, logs_mode in views:
            backend.setActivePage(page)
            if logs_mode is not None:
                backend.setLogsMode(logs_mode)
            for width, height in sizes:
                window.setWidth(width)
                window.setHeight(height)
                _settle(app)
                key = f"{language}-{view_name}-{width}x{height}"
                current = _text_issues(window)
                if current:
                    issues[key] = current
                image = window.grabWindow()
                target = args.screenshots_dir / f"{key}.png"
                if image.isNull() or not image.save(str(target)):
                    issues.setdefault(key, []).append("screenshot-failed")
                else:
                    captures.append(str(target))

    runtime_after = _runtime_fingerprint(ctx) if args.live_readonly else None
    runtime_unchanged = (
        runtime_before == runtime_after
        if args.live_readonly
        else True
    )
    if not runtime_unchanged:
        issues.setdefault("runtime-invariant", []).append(
            "live-readonly verification changed managed runtime identity"
        )

    result = {
        "ok": not issues,
        "mode": "live-readonly" if args.live_readonly else "fixture",
        "captures": len(captures),
        "screenshots_dir": str(args.screenshots_dir),
        "issues": issues,
        "font": {
            "ui": backend.uiFontFamily,
            "mono": backend.monoFontFamily,
        },
        "safe_actions": True,
        "runtime_unchanged": runtime_unchanged,
    }
    if args.live_readonly:
        result["runtime_before"] = runtime_before
        result["runtime_after"] = runtime_after
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Stop Python workers, then terminate like the real application. Do
    # not force an extra QML destruction/event-processing pass after removing
    # the context object; that only re-evaluates bindings during teardown.
    mark_qt_shutting_down()
    backend.shutdown()
    app.quit()
    verification_state.cleanup()
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
