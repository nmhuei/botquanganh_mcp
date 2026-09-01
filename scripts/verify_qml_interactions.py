#!/usr/bin/env python3
"""Exercise the minimal BQA Center GUI through a real QQuickWindow."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from app.cli.center.persistence import CenterWindowStateStore
from app.cli.context import CLIContext
from app.cli.ui_preferences import UIPreferencesStore
from app.qml_ui.app import create_qml_runtime, mark_qt_shutting_down


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def settle(app: QGuiApplication, ms: int = 70) -> None:
    QTest.qWait(ms)
    app.processEvents()


def walk_visual(item):
    yield item
    if hasattr(item, "childItems"):
        for child in item.childItems():
            yield from walk_visual(child)


def visible(item) -> bool:
    return hasattr(item, "isVisible") and bool(item.isVisible())


def find_object(window, object_name: str):
    for item in walk_visual(window.contentItem()):
        if item.objectName() == object_name:
            return item
    return None


def find_visual_with(window, **props):
    for item in walk_visual(window.contentItem()):
        if not visible(item):
            continue
        meta = item.metaObject()
        if all(
            meta.indexOfProperty(key) >= 0 and item.property(key) == expected
            for key, expected in props.items()
        ):
            return item
    return None


def find_clickable_text(window, text: str, occurrence: int = 0):
    matches = []
    for item in walk_visual(window.contentItem()):
        if not visible(item):
            continue
        class_name = item.metaObject().className()
        if not any(name in class_name for name in ("ClassicButton", "NavItem", "SortHeader")):
            continue
        meta = item.metaObject()
        if meta.indexOfProperty("text") < 0:
            continue
        if str(item.property("text") or "") != text:
            continue
        point = item.mapToScene(QPointF(float(item.width()) / 2, float(item.height()) / 2))
        matches.append((point.y(), point.x(), item))
    matches.sort(key=lambda row: (row[0], row[1]))
    require(len(matches) > occurrence, f"Clickable {text!r} occurrence {occurrence} missing")
    return matches[occurrence][2]


def click(window, item):
    require(item is not None, "Missing click target")
    require(visible(item), f"Click target not visible: {item}")
    if item.metaObject().indexOfProperty("enabled") >= 0:
        require(bool(item.property("enabled")), f"Click target disabled: {item}")
    point = item.mapToScene(
        QPointF(float(item.width()) / 2, float(item.height()) / 2)
    ).toPoint()
    require(
        0 <= point.x() < window.width() and 0 <= point.y() < window.height(),
        f"Click target outside window: {point}",
    )
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)


def click_object(window, object_name: str):
    item = find_object(window, object_name)
    require(item is not None, f"{object_name} object missing")
    click(window, item)
    return item


def click_text(window, text: str, occurrence: int = 0):
    item = find_clickable_text(window, text, occurrence)
    click(window, item)
    return item


def main() -> int:
    checks: list[str] = []
    with TemporaryDirectory(prefix="bqa-qml-interaction-") as temp:
        root = Path(temp)
        ctx = CLIContext(
            repo_root=root,
            values={"HOST_CHAT_ROOT": str(root / "chats"), "MCP_PORT": "18427"},
            base_url="http://127.0.0.1:18427",
            token="",
            request_timeout=1.0,
        )
        app, engine, backend = create_qml_runtime(
            ctx,
            fixture=True,
            safe_actions=True,
            preferences_store=UIPreferencesStore(root / "ui.json"),
            window_state_store=CenterWindowStateStore(root / "window.json"),
        )
        app.setQuitOnLastWindowClosed(False)
        window = engine.rootObjects()[0]
        window.setWidth(1366)
        window.setHeight(900)

        try:
            window.requestActivate()
            require(QTest.qWaitForWindowActive(window, 1500), "QML window did not activate")
            settle(app, 120)

            # Three primary GUI views: both click and keyboard navigation.
            for object_name, page in (
                ("navOverview", "overview"),
                ("navActivity", "activity"),
                ("navLogs", "logs"),
            ):
                click_object(window, object_name)
                settle(app)
                require(backend.activePage == page, f"{object_name} did not open {page}")
            checks.append("three_primary_views_mouse")

            for key, page in (
                (Qt.Key_1, "overview"),
                (Qt.Key_2, "activity"),
                (Qt.Key_3, "logs"),
            ):
                QTest.keyClick(window, key, Qt.ControlModifier)
                settle(app)
                require(backend.activePage == page, f"Ctrl+{key - Qt.Key_0} did not open {page}")
            checks.append("three_primary_views_keyboard")

            # Activity search, sorting, selection and operation -> logs cross-navigation.
            QTest.keyClick(window, Qt.Key_2, Qt.ControlModifier)
            settle(app)
            QTest.keyClick(window, Qt.Key_F, Qt.ControlModifier)
            settle(app, 40)
            operation_search = find_object(window, "operationSearch")
            require(operation_search is not None and bool(operation_search.property("activeFocus")),
                    "Ctrl+F did not focus Activity search")
            operation_search.setProperty("text", "status:failed")
            settle(app, 190)
            rows = backend.operationsModel.rows()
            require(rows and all(row["status"] == "failed" for row in rows),
                    "Activity search did not filter failed rows")
            operation_search.setProperty("text", "")
            backend.setOperationSearch("")
            settle(app, 190)

            duration_header = click_object(window, "sortDurationHeader")
            settle(app)
            ascending = [float(row["duration"]) for row in backend.operationsModel.rows()]
            require(ascending == sorted(ascending), "Duration header did not sort ascending")
            duration_header.forceActiveFocus()
            QTest.keyClick(window, Qt.Key_Space)
            settle(app)
            descending = [float(row["duration"]) for row in backend.operationsModel.rows()]
            require(descending == sorted(descending, reverse=True), "Keyboard sort did not reverse")
            checks.append("activity_search_sort")

            operation_id = backend.operationsModel.get(0)["operationId"]
            operation_row = find_visual_with(window, operationId=operation_id)
            require(operation_row is not None, "Operation row missing")
            click(window, operation_row)
            settle(app)
            require(backend.selectedOperationId == operation_id, "Operation selection failed")
            activity_page = find_object(window, "activityPage")
            require(activity_page is not None and bool(activity_page.property("inspectorOpen")),
                    "Operation detail drawer did not open")
            click_object(window, "relatedLogsButton")
            settle(app)
            require(
                backend.activePage == "logs"
                and backend.logsMode == "events"
                and backend.logsModel.rowCount() > 0
                and all(row["operationId"] == operation_id for row in backend.logsModel.rows()),
                "Operation -> related logs cross-navigation failed",
            )
            checks.append("activity_drawer_crossnav")

            # Event-log search and log -> operation cross-navigation.
            backend.clearLogFilters()
            settle(app)
            QTest.keyClick(window, Qt.Key_F, Qt.ControlModifier)
            settle(app, 40)
            event_search = find_object(window, "eventLogSearch")
            require(event_search is not None and bool(event_search.property("activeFocus")),
                    "Ctrl+F did not focus event search")
            event_search.setProperty("text", "severity:error")
            settle(app, 190)
            log_rows = backend.logsModel.rows()
            require(log_rows and all(row["severity"] == "ERROR" for row in log_rows),
                    "Event search did not filter errors")
            event_search.setProperty("text", "")
            backend.setLogSearch("")
            backend.clearLogFilters()
            settle(app, 190)

            target = next(row for row in backend.logsModel.rows() if row["operationId"])
            log_row = find_visual_with(window, eventId=target["eventId"])
            require(log_row is not None, "Event row missing")
            click(window, log_row)
            settle(app)
            require(backend.selectedLogId == target["eventId"], "Event selection failed")
            logs_page = find_object(window, "logsPage")
            require(logs_page is not None and bool(logs_page.property("inspectorOpen")),
                    "Event detail drawer did not open")
            click_object(window, "openOperationButton")
            settle(app)
            require(
                backend.activePage == "activity"
                and backend.selectedOperationId == target["operationId"],
                "Log -> operation cross-navigation failed",
            )
            checks.append("event_logs_search_crossnav")

            # Runtime mode uses a separate searchable table with keyboard selection.
            click_object(window, "navLogs")
            settle(app)
            click_object(window, "logsRuntimeMode")
            settle(app)
            require(backend.logsMode == "runtime", "Runtime mode button did not switch mode")
            QTest.keyClick(window, Qt.Key_F, Qt.ControlModifier)
            settle(app, 40)
            runtime_search = find_object(window, "runtimeLogSearch")
            require(runtime_search is not None and bool(runtime_search.property("activeFocus")),
                    "Ctrl+F did not focus runtime search")
            runtime_search.setProperty("text", "warning")
            settle(app, 190)
            runtime_rows = backend.runtimeLogsModel.rows()
            require(runtime_rows and all("warning" in row["line"].lower() for row in runtime_rows),
                    "Runtime search returned unrelated rows")
            runtime_search.setProperty("text", "")
            backend.setRuntimeLogSearch("")
            backend.setRuntimeLogSource("all")
            settle(app, 190)

            runtime_list = find_object(window, "runtimeLogList")
            require(runtime_list is not None, "Runtime list missing")
            runtime_list.setProperty("currentIndex", -1)
            runtime_list.forceActiveFocus()
            QTest.keyClick(window, Qt.Key_Down)
            settle(app)
            selected_index = int(runtime_list.property("currentIndex"))
            require(selected_index >= 0, "Runtime keyboard selection did not move")
            first = backend.runtimeLogsModel.get(selected_index)
            require(
                str(logs_page.property("runtimeSelectedLine") or "") == first["line"],
                "Runtime keyboard/current selection did not project detail",
            )
            checks.append("runtime_logs_search_selection")

            # Secondary capabilities live in the overflow menu instead of primary nav.
            backend.setActivePage("overview")
            settle(app)
            for menu_object, expected_page in (
                ("menuWorkspaces", "workspaces"),
                ("menuDiagnostics", "diagnostics"),
                ("menuPreferences", "settings"),
            ):
                click_object(window, "appMenuButton")
                settle(app, 40)
                click_object(window, menu_object)
                settle(app, 90)
                require(backend.activePage == expected_page,
                        f"{menu_object} did not open {expected_page}")
                backend.setActivePage("overview")
                settle(app, 70)
            checks.append("secondary_surfaces_overflow")

            # Preferences hot-apply through the real GUI.
            click_object(window, "appMenuButton")
            settle(app, 40)
            click_object(window, "menuPreferences")
            settle(app)
            workspace_field = find_object(window, "workspaceField")
            require(workspace_field is not None, "Preferences workspace field missing")
            before_height = float(workspace_field.property("implicitHeight"))
            before_font = int(workspace_field.property("font").pixelSize())

            click_object(window, "settingsLanguageVietnamese")
            settle(app)
            require(backend.language == "vi", "Language did not hot-apply")
            click_object(window, "settingsTheme-light")
            settle(app)
            require(backend.themeName == "light", "Theme did not hot-apply")
            click_object(window, "settingsDensityComfortable")
            settle(app)
            require(
                backend.density == "comfortable"
                and float(workspace_field.property("implicitHeight")) > before_height,
                "Density did not resize controls",
            )
            click_object(window, "settingsFontScaleUp")
            settle(app)
            require(
                backend.fontScale > 1.0
                and int(workspace_field.property("font").pixelSize()) > before_font,
                "Font scale did not change rendered font",
            )
            require(not (root / ".env").exists(), "Preferences unexpectedly touched .env")
            checks.append("preferences_hot_apply")

            # Toast remains transient and the GUI exposes no tunnel-stop capability.
            backend.copyText("interaction-check")
            require(backend.toastText == "Copied", "Copy toast not emitted")
            settle(app, 3500)
            require(backend.toastText == "", "Toast did not auto-dismiss")
            checks.append("toast_auto_dismiss")

            method_names = {
                bytes(backend.metaObject().method(index).name()).decode("utf-8")
                for index in range(
                    backend.metaObject().methodOffset(),
                    backend.metaObject().methodCount(),
                )
            }
            require("stopService" not in method_names, "QML backend exposes stopService")
            checks.append("no_tunnel_stop_surface")

            print(json.dumps({"ok": True, "checks": checks, "count": len(checks)}, indent=2))
            return 0
        finally:
            mark_qt_shutting_down()
            backend.shutdown()
            window.close()
            app.quit()


if __name__ == "__main__":
    raise SystemExit(main())
