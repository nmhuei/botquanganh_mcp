#!/usr/bin/env python3
"""Verify the remade BQA Center GUI across desktop viewport profiles."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time

from PySide6.QtCore import QObject
from PySide6.QtGui import QGuiApplication

from app.cli.center.persistence import CenterWindowStateStore
from app.cli.context import CLIContext
from app.cli.ui_preferences import UIPreferencesStore
from app.qml_ui.app import create_qml_runtime, mark_qt_shutting_down
from scripts.verify_qml_ui import _text_issues


VIEWS = (
    ("monitor", "overview", "overviewPage", None, True),
    ("activity", "activity", "activityPage", None, False),
    ("logs-events", "logs", "logsPage", "events", False),
    ("logs-runtime", "logs", "logsPage", "runtime", False),
    ("workspaces", "workspaces", "workspacesPage", None, True),
    ("diagnostics", "diagnostics", "diagnosticsPage", None, True),
    ("preferences", "settings", "settingsPage", None, True),
)

SIZES = (
    (960, 650),
    (1180, 760),
    (1366, 768),
    (1600, 900),
)


def _ctx(root: Path) -> CLIContext:
    return CLIContext(
        repo_root=root,
        values={
            "HOST_CHAT_ROOT": str(root / "chats"),
            "MCP_PORT": "18427",
        },
        base_url="http://127.0.0.1:18427",
        token="",
        request_timeout=1.0,
    )


def _settle(app: QGuiApplication, milliseconds: int = 90) -> None:
    deadline = time.monotonic() + milliseconds / 1000.0
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


def _visual_children(item):
    if not hasattr(item, "childItems"):
        return []
    return [child for child in item.childItems() if child.isVisible()]


def _largest_child(item):
    children = _visual_children(item)
    if not children:
        return None
    return max(children, key=lambda child: float(child.width()) * float(child.height()))


def _large_page_flickables(item):
    offenders = []
    for child in _visual_children(item):
        class_name = child.metaObject().className()
        if "Flickable" not in class_name and "ScrollView" not in class_name:
            continue
        if (
            float(child.width()) >= float(item.width()) * 0.8
            and float(child.height()) >= float(item.height()) * 0.8
        ):
            offenders.append(class_name)
    return offenders


def _check_geometry(page, viewport) -> list[str]:
    issues: list[str] = []
    tolerance = 3.0
    x = float(viewport.x())
    y = float(viewport.y())
    width = float(viewport.width())
    height = float(viewport.height())
    page_width = float(page.width())
    page_height = float(page.height())

    if x < -tolerance or y < -tolerance:
        issues.append(f"negative-origin:{x:.1f},{y:.1f}")
    if x + width > page_width + tolerance:
        issues.append(f"viewport-width:{x + width:.1f}>{page_width:.1f}")
    if y + height > page_height + tolerance:
        issues.append(f"viewport-height:{y + height:.1f}>{page_height:.1f}")
    return issues


def main() -> int:
    with TemporaryDirectory(prefix="bqa-qml-viewport-fit-") as temp:
        root = Path(temp)
        app, engine, backend = create_qml_runtime(
            _ctx(root),
            fixture=True,
            safe_actions=True,
            preferences_store=UIPreferencesStore(root / "ui.json"),
            window_state_store=CenterWindowStateStore(root / "window.json"),
        )
        app.setQuitOnLastWindowClosed(False)
        window = engine.rootObjects()[0]

        issues: dict[str, list[str]] = {}
        measurements: dict[str, dict[str, float | int | str | bool]] = {}

        try:
            profiles = (
                ("default", "en", "compact", 1.0, SIZES),
                ("stress-vi-140", "vi", "comfortable", 1.4, ((960, 650),)),
            )

            for profile, language, density, font_scale, sizes in profiles:
                backend.changeLanguage(language)
                backend.changeDensity(density)
                backend.changeFontScale(font_scale)

                for width, height in sizes:
                    window.setWidth(width)
                    window.setHeight(height)
                    _settle(app)

                    for view_name, page_name, object_name, logs_mode, scroll_allowed in VIEWS:
                        backend.setActivePage(page_name)
                        if logs_mode is not None:
                            backend.setLogsMode(logs_mode)
                        _settle(app)

                        page = window.findChild(QObject, object_name)
                        key = f"{profile}:{view_name}:{width}x{height}"
                        if page is None:
                            issues.setdefault(key, []).append("page-root-missing")
                            continue

                        viewport = _largest_child(page)
                        if viewport is None:
                            issues.setdefault(key, []).append("top-level-viewport-missing")
                            continue

                        geometry_issues = _check_geometry(page, viewport)
                        if geometry_issues:
                            issues.setdefault(key, []).extend(geometry_issues)

                        flickables = _large_page_flickables(page)
                        if flickables and not scroll_allowed:
                            issues.setdefault(key, []).append(
                                "unexpected-page-level-scroll:" + ",".join(flickables)
                            )

                        text_issues = _text_issues(window)
                        if text_issues:
                            issues.setdefault(key, []).extend(text_issues[:12])

                        measurements[key] = {
                            "page_width": round(float(page.width()), 1),
                            "page_height": round(float(page.height()), 1),
                            "viewport_width": round(float(viewport.width()), 1),
                            "viewport_height": round(float(viewport.height()), 1),
                            "top_level_type": viewport.metaObject().className(),
                            "scroll_allowed": scroll_allowed,
                        }

            result = {
                "ok": not issues,
                "issues": issues,
                "checks": len(measurements),
                "profiles": ["default", "stress-vi-140"],
                "sizes": [f"{w}x{h}" for w, h in SIZES],
                "primary_data_views_page_scroll": False,
                "monitor_and_secondary_scroll_allowed": True,
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result["ok"] else 1
        finally:
            mark_qt_shutting_down()
            backend.shutdown()
            app.quit()


if __name__ == "__main__":
    raise SystemExit(main())
