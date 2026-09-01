"""Application bootstrap for the QML BQA Center frontend."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any

from PySide6.QtCore import QUrl, qInstallMessageHandler
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine
from PySide6.QtQuickControls2 import QQuickStyle

from app.cli.center.persistence import CenterWindowStateStore
from app.cli.ui_preferences import UIPreferencesStore
from app.qml_ui.backend import CenterQmlBackend


QML_ROOT = Path(__file__).resolve().parent / "qml"


_qt_shutting_down = False
_qt_message_filter_installed = False


def _qt_message_handler(_mode: Any, context: Any, message: str) -> None:
    """Preserve Qt diagnostics except context-null noise during teardown."""
    if _qt_shutting_down and "Cannot read property" in message and "of null" in message:
        return
    location = ""
    file_name = getattr(context, "file", None)
    line = getattr(context, "line", None)
    if file_name:
        location = f"{file_name}:{line or 0}: "
    sys.stderr.write(f"{location}{message}\n")
    sys.stderr.flush()


def _install_qt_message_filter() -> None:
    global _qt_message_filter_installed
    if _qt_message_filter_installed:
        return
    qInstallMessageHandler(_qt_message_handler)
    _qt_message_filter_installed = True


def mark_qt_shutting_down() -> None:
    global _qt_shutting_down
    _qt_shutting_down = True


def mark_qt_running() -> None:
    """Reset teardown-only diagnostic filtering for a fresh QML runtime."""
    global _qt_shutting_down
    _qt_shutting_down = False


class QmlUIUnavailable(RuntimeError):
    """Raised when Qt Quick cannot initialize the desktop frontend."""


def create_qml_runtime(
    ctx: Any,
    *,
    fixture: bool = False,
    safe_actions: bool = False,
    preferences_store: UIPreferencesStore | None = None,
    window_state_store: CenterWindowStateStore | None = None,
) -> tuple[QGuiApplication, QQmlApplicationEngine, CenterQmlBackend]:
    """Build but do not enter the QML event loop."""
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    QQuickStyle.setStyle("Basic")
    mark_qt_running()
    _install_qt_message_filter()

    app = QGuiApplication.instance()
    if app is None:
        app = QGuiApplication(sys.argv[:1])
    app.setApplicationName("BQA Center")
    app.setOrganizationName("UCS")

    backend = CenterQmlBackend(
        ctx,
        fixture=fixture,
        safe_actions=safe_actions,
        preferences_store=preferences_store,
        window_state_store=window_state_store,
    )
    # The Python bootstrap owns the backend lifecycle. Prevent QQmlEngine from
    # reclaiming the context object before QML bindings are torn down.
    QQmlEngine.setObjectOwnership(backend, QQmlEngine.CppOwnership)
    app.setFont(QFont(backend.uiFontFamily))
    engine = QQmlApplicationEngine()
    engine.setInitialProperties({"center": backend})
    engine.addImportPath(str(QML_ROOT))
    engine.load(QUrl.fromLocalFile(str(QML_ROOT / "Main.qml")))
    if not engine.rootObjects():
        backend.shutdown()
        raise QmlUIUnavailable("Qt Quick failed to load the BQA Center QML tree.")
    app.aboutToQuit.connect(mark_qt_shutting_down)
    app.aboutToQuit.connect(backend.shutdown)
    return app, engine, backend


def run_qml_ui(
    ctx: Any,
    *,
    fixture: bool = False,
    safe_actions: bool = False,
) -> int:
    """Open the QML desktop frontend and block until the window closes."""
    app, _engine, _backend = create_qml_runtime(
        ctx,
        fixture=fixture,
        safe_actions=safe_actions,
    )
    return int(app.exec())
