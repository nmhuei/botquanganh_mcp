#!/usr/bin/env python3
"""Functional verification for the minimal BQA Center GUI.

The fixture uses safe_actions=True, so lifecycle/workspace mutation actions
prove QML/backend wiring without changing live services or real workspaces.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time

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


def walk(item):
    yield item
    if hasattr(item, "childItems"):
        for child in item.childItems():
            yield from walk(child)


def visible(item) -> bool:
    return hasattr(item, "isVisible") and bool(item.isVisible())


def find_object(window, name: str):
    for item in walk(window.contentItem()):
        if item.objectName() == name:
            return item
    return None


def find_with(window, **props):
    for item in walk(window.contentItem()):
        if not visible(item):
            continue
        meta = item.metaObject()
        if all(meta.indexOfProperty(k) >= 0 and item.property(k) == v for k, v in props.items()):
            return item
    return None


def find_text(window, text: str, occurrence: int = 0):
    matches = []
    for item in walk(window.contentItem()):
        if not visible(item):
            continue
        cls = item.metaObject().className()
        if not any(name in cls for name in ("ClassicButton", "NavItem", "SortHeader")):
            continue
        meta = item.metaObject()
        if meta.indexOfProperty("text") < 0 or str(item.property("text") or "") != text:
            continue
        point = item.mapToScene(QPointF(float(item.width()) / 2, float(item.height()) / 2))
        matches.append((point.y(), point.x(), item))
    matches.sort(key=lambda row: (row[0], row[1]))
    require(len(matches) > occurrence, f"Clickable {text!r} occurrence {occurrence} missing")
    return matches[occurrence][2]


def click(window, item) -> None:
    require(item is not None, "Missing click target")
    require(visible(item), f"Click target not visible: {item}")
    if item.metaObject().indexOfProperty("enabled") >= 0:
        require(bool(item.property("enabled")), f"Disabled click target: {item}")
    point = item.mapToScene(QPointF(float(item.width()) / 2, float(item.height()) / 2)).toPoint()
    require(0 <= point.x() < window.width() and 0 <= point.y() < window.height(),
            f"Click target outside window: {point}")
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)


def click_object(window, name: str):
    item = find_object(window, name)
    require(item is not None, f"{name} missing")
    click(window, item)
    return item


def wait_safe_action(backend, app: QGuiApplication, label: str) -> str:
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        app.processEvents()
        if not backend.actionBusy and backend.toastText:
            break
        QTest.qWait(10)
    require(not backend.actionBusy, f"{label}: action stayed busy")
    require(backend.toastText.startswith("SAFE VERIFY:"), f"{label}: unsafe/unexpected result {backend.toastText!r}")
    value = backend.toastText
    backend.clearToast()
    return value


def main() -> int:
    checks: list[str] = []
    with TemporaryDirectory(prefix="bqa-qml-functional-") as temp:
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

            # Primary navigation is intentionally limited to Monitor, Activity, Logs.
            for name, page in (
                ("navOverview", "overview"),
                ("navActivity", "activity"),
                ("navLogs", "logs"),
            ):
                click_object(window, name)
                settle(app)
                require(backend.activePage == page, f"{name} did not navigate")
            require(find_object(window, "navWorkspaces") is None, "Workspaces leaked back into primary navigation")
            require(find_object(window, "navDiagnostics") is None, "Diagnostics leaked back into primary navigation")
            require(find_object(window, "navSettings") is None, "Settings leaked back into primary navigation")
            checks.append("minimal_primary_navigation")

            # Safe lifecycle action is still reachable through overflow.
            backend.setActivePage("overview")
            settle(app)
            click_object(window, "appMenuButton")
            settle(app, 40)
            restart_button = find_text(window, "Restart connector")
            click(window, restart_button)
            wait_safe_action(backend, app, "restart connector")
            checks.append("overflow_lifecycle_action")

            # Activity session controls remain available progressively.
            click_object(window, "navActivity")
            settle(app)
            first_session = backend.sessionsModel.get(0)["chatId"]
            session_row = find_with(window, chatId=first_session)
            require(session_row is not None, "Session row not rendered")
            click(window, session_row)
            settle(app)
            require(backend.selectedSessionId == first_session, "Session selection failed")
            click_object(window, "sessionMenuButton")
            settle(app, 40)

            track = find_text(window, "Mute")
            click(window, track)
            settle(app)
            require(
                backend.sessionsModel.get(backend.sessionsModel.find(first_session))["tracked"] is False,
                "Mute did not change local tracking",
            )
            click_object(window, "sessionMenuButton")
            settle(app, 40)
            click(window, find_text(window, "Track"))
            settle(app)
            require(
                backend.sessionsModel.get(backend.sessionsModel.find(first_session))["tracked"] is True,
                "Track did not restore tracking",
            )
            checks.append("activity_progressive_session_controls")

            # Operation drawer actions are real.
            backend.showAllSessions()
            settle(app)
            operation_id = backend.operationsModel.get(0)["operationId"]
            operation_row = find_with(window, operationId=operation_id)
            require(operation_row is not None, "Operation row missing")
            click(window, operation_row)
            settle(app)
            activity_page = find_object(window, "activityPage")
            require(bool(activity_page.property("inspectorOpen")), "Activity drawer did not open")
            click(window, find_text(window, "Copy tab"))
            settle(app)
            require(backend.toastText == "Copied" and QGuiApplication.clipboard().text() != "",
                    "Activity copy action failed")
            backend.clearToast()
            click_object(window, "relatedLogsButton")
            settle(app)
            require(
                backend.activePage == "logs"
                and all(row["operationId"] == operation_id for row in backend.logsModel.rows()),
                "Related logs action failed",
            )
            checks.append("activity_drawer_actions")

            # Event filtering remains reachable in one compact popover.
            backend.clearLogFilters()
            settle(app)
            click_object(window, "logsFilterButton")
            settle(app, 40)
            click(window, find_text(window, "Errors"))
            settle(app)
            require(
                backend.logCategoryFilter == "error"
                and backend.logsModel.rowCount() > 0
                and all(row["severity"] == "ERROR" or row["outcome"] == "failure" for row in backend.logsModel.rows()),
                "Errors filter did not apply",
            )
            click(window, find_text(window, "Failure"))
            settle(app)
            require(
                backend.logOutcomeFilter == "failure"
                and all(row["outcome"] == "failure" for row in backend.logsModel.rows()),
                "Failure outcome did not apply",
            )
            backend.clearLogFilters()
            checks.append("logs_filter_popover")

            # Runtime source/search remains independent.
            click_object(window, "logsRuntimeMode")
            settle(app)
            click_object(window, "logsFilterButton")
            settle(app, 40)
            click(window, find_text(window, "Tunnel"))
            settle(app)
            require(
                backend.runtimeLogSource == "tunnel"
                and backend.runtimeLogsModel.rowCount() == 12
                and all(row["source"] == "tunnel" for row in backend.runtimeLogsModel.rows()),
                "Runtime Tunnel source filter failed",
            )
            checks.append("runtime_source_filter")

            # Workspace manager is secondary but functional and cross-navigates.
            backend.setActivePage("overview")
            settle(app)
            click_object(window, "appMenuButton")
            settle(app, 40)
            click_object(window, "menuWorkspaces")
            settle(app)
            require(backend.activePage == "workspaces", "Workspace manager did not open")
            workspace_id = backend.workspacesModel.get(0)["chatId"]
            workspace_row = find_with(window, chatId=workspace_id, label=backend.workspacesModel.get(0)["label"])
            require(workspace_row is not None, "Workspace row missing")
            click(window, workspace_row)
            settle(app)
            click_object(window, "workspaceOpenActivity")
            settle(app)
            require(
                backend.activePage == "activity" and backend.selectedSessionId == workspace_id,
                "Workspace -> Activity cross-navigation failed",
            )
            checks.append("workspace_manager_crossnav")

            # Diagnostics is an on-demand surface and the full doctor is wired.
            backend.setActivePage("overview")
            settle(app)
            click_object(window, "appMenuButton")
            settle(app, 40)
            click_object(window, "menuDiagnostics")
            settle(app)
            click(window, find_text(window, "Run full doctor"))
            settle(app, 120)
            require(
                backend.doctorChecksModel.rowCount() > 0 and backend.doctorBusy is False,
                "Full doctor did not execute",
            )
            checks.append("diagnostics_on_demand")

            # Preferences remain hot and UI-only.
            backend.setActivePage("overview")
            settle(app)
            click_object(window, "appMenuButton")
            settle(app, 40)
            click_object(window, "menuPreferences")
            settle(app)
            click_object(window, "settingsTheme-light")
            settle(app)
            click_object(window, "settingsDensityComfortable")
            settle(app)
            click_object(window, "settingsFontScaleUp")
            settle(app)
            require(
                backend.themeName == "light"
                and backend.density == "comfortable"
                and backend.fontScale > 1.0,
                "Preferences did not hot-apply",
            )
            require(not (root / ".env").exists(), "Preferences touched .env")
            checks.append("preferences_ui_only")

            method_names = {
                bytes(backend.metaObject().method(index).name()).decode("utf-8")
                for index in range(backend.metaObject().methodOffset(), backend.metaObject().methodCount())
            }
            require("stopService" not in method_names, "stopService exposed to QML")
            checks.append("no_tunnel_stop_control_or_slot")

            result = {
                "ok": True,
                "safe_actions": True,
                "checks": checks,
                "count": len(checks),
                "models": {
                    "sessions": backend.sessionsModel.rowCount(),
                    "operations": backend.operationsModel.rowCount(),
                    "workspaces": backend.workspacesModel.rowCount(),
                    "runtime_logs": backend.runtimeLogsModel.rowCount(),
                    "doctor_checks": backend.doctorChecksModel.rowCount(),
                },
            }
            print(json.dumps(result, indent=2))
            return 0
        finally:
            mark_qt_shutting_down()
            backend.shutdown()
            window.close()
            app.quit()


if __name__ == "__main__":
    raise SystemExit(main())
