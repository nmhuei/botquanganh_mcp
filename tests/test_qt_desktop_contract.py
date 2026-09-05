import builtins
import os
import queue
import threading
import time
import tomllib
from pathlib import Path

import pytest

from app.cli.desktop_identity import (
    DESKTOP_APP_NAME,
    DESKTOP_IDENTITY_TEXT,
    desktop_app_icon_path,
)


@pytest.fixture
def qapp():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_visual_remake_primitives_expose_compact_brand_and_icon_rail(qapp):
    from PySide6 import QtGui, QtWidgets
    from app.cli.desktop_qt.theme import COLORS, LAYOUT, build_stylesheet
    from app.cli.desktop_qt.widgets import (
        FooterStatusItem,
        HeaderBrand,
        IconRailItem,
        PanelFrame,
        SectionHeading,
    )

    brand = HeaderBrand(QtWidgets, QtGui)
    rail_item = IconRailItem(QtWidgets, "Runtime", "⌁", lambda: None)
    heading = SectionHeading(QtWidgets, "Runtime", "COMMAND")
    panel = PanelFrame(QtWidgets)
    footer_item = FooterStatusItem(QtWidgets, "backend: ready")

    assert brand.app_name_label.text() == "UCS-SecretAgent"
    assert brand.identity_label.text() == "UCS // SECRET AGENT"
    assert brand.widget.objectName() == "commandBrand"
    assert rail_item.button.objectName() == "iconRailItem"
    assert rail_item.button.accessibleName() == "Runtime"
    assert rail_item.button.property("active") == "true"
    assert heading.title_label.text() == "Runtime"
    assert heading.eyebrow_label.text() == "COMMAND"
    assert panel.widget.objectName() == "panelFrame"
    assert panel.layout.spacing() == LAYOUT["space_sm"]
    assert footer_item.widget.text() == "backend: ready"
    assert footer_item.widget.property("role") == "footerStatus"
    assert LAYOUT["header_height"] == 64
    assert LAYOUT["rail_width"] == 76
    assert COLORS["canvas"] == "#090d0c"
    assert "QFrame#commandHeader" in build_stylesheet()
    assert "QPushButton#iconRailItem:focus" in build_stylesheet()


def test_visual_system_primitives_expose_presentation_widgets(qapp):
    from PySide6 import QtWidgets
    from app.cli.desktop_qt.widgets import (
        DetailRow,
        InspectorFrame,
        MetricCell,
        ServiceDetailCard,
    )

    metric = MetricCell(QtWidgets, "Active", "3")
    detail = DetailRow(QtWidgets, "Endpoint", "https://localhost/mcp")
    service_card = ServiceDetailCard(QtWidgets, "Bridge")
    inspector = InspectorFrame(QtWidgets, "Payload")

    assert metric.widget.objectName() == "metricCell"
    assert metric.label.text() == "Active"
    assert metric.value.text() == "3"
    assert detail.widget.objectName() == "detailRow"
    assert detail.label.text() == "Endpoint"
    assert detail.value.text() == "https://localhost/mcp"
    assert service_card.widget.objectName() == "serviceDetailCard"
    assert service_card.title.text() == "Bridge"
    assert inspector.widget.objectName() == "inspectorSurface"
    assert inspector.title.text() == "Payload"


def test_cli_docs_describe_qt_desktop_ui():
    text = Path("docs/CLI_UI.md").read_text(encoding="utf-8")

    assert "PySide6" in text
    assert "native Tkinter" not in text
    assert "UCS-SecretAgent" in text
    assert "bqa ui" in text


def test_qt_dependency_uses_essentials_not_full_pyside():
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]

    assert "PySide6-Essentials>=6.8,<7" in dependencies
    assert not any(item == "PySide6" or item.startswith("PySide6==") for item in dependencies)
    assert not any("PySide6-Addons" in item or "WebEngine" in item for item in dependencies)


def test_desktop_identity_keeps_existing_name_and_logo():
    assert DESKTOP_APP_NAME == "UCS-SecretAgent"
    assert DESKTOP_IDENTITY_TEXT == "UCS // SECRET AGENT"
    assert desktop_app_icon_path().name == "ucs-secretagent.png"
    assert desktop_app_icon_path().is_file()


def test_qt_binding_error_mentions_installable_package(monkeypatch):
    import app.cli.desktop_qt.compat as compat

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "PySide6":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(compat.QtBindingError) as excinfo:
        compat.load_qt_bindings()

    text = str(excinfo.value)
    assert "PySide6-Essentials" in text
    assert "bqa ui" in text


def test_qt_theme_has_balanced_ucs_tokens():
    from app.cli.desktop_qt.theme import COLORS, build_stylesheet

    assert COLORS["canvas"].startswith("#")
    assert COLORS["lime"] == "#a3ff12"
    assert COLORS["danger"] != COLORS["lime"]
    assert COLORS["success"] != COLORS["lime"]
    assert "QMainWindow" in build_stylesheet()
    assert "border-radius: 8px" in build_stylesheet()


def test_logo_loader_reads_existing_png_when_qt_available():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtGui, QtWidgets
    from app.cli.desktop_qt.widgets import load_logo_pixmap

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    pixmap = load_logo_pixmap(QtGui, size=52)

    assert application is not None
    assert pixmap is not None
    assert pixmap.width() <= 52
    assert pixmap.height() <= 52


def test_run_desktop_ui_routes_to_qt(monkeypatch, tmp_path):
    from app.cli.context import CLIContext
    import app.cli.desktop_ui as desktop_ui

    calls = []

    def fake_run(ctx, **kwargs):
        calls.append((ctx, kwargs))
        return 0

    monkeypatch.setattr("app.cli.desktop_qt.app.run_qt_desktop_ui", fake_run)
    ctx = CLIContext(
        repo_root=tmp_path,
        values={},
        base_url="http://127.0.0.1:18427",
        token="",
        request_timeout=1.0,
    )

    assert desktop_ui.run_desktop_ui(ctx) == 0
    assert calls[0][0] is ctx


def test_run_desktop_ui_converts_qt_binding_error(monkeypatch, tmp_path):
    from app.cli.context import CLIContext
    import app.cli.desktop_ui as desktop_ui
    from app.cli.desktop_qt.compat import QtBindingError

    def fail(_ctx, **_kwargs):
        raise QtBindingError("missing PySide6-Essentials")

    monkeypatch.setattr("app.cli.desktop_qt.app.run_qt_desktop_ui", fail)

    with pytest.raises(desktop_ui.DesktopUIUnavailable) as excinfo:
        desktop_ui.run_desktop_ui(
            CLIContext(
                repo_root=tmp_path,
                values={},
                base_url="http://127.0.0.1:18427",
                token="",
                request_timeout=1.0,
            )
        )

    assert "PySide6-Essentials" in str(excinfo.value)


def _qt_dashboard(tmp_path, **overrides):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtWidgets
    from app.cli.context import CLIContext
    from app.cli.desktop_qt.app import QtDesktopDashboard
    from app.cli.desktop_qt.compat import load_qt_bindings

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    values = {
        "HOST_CHAT_ROOT": str(tmp_path / "chats"),
        "HOST_WORKSPACE_DIR": str(tmp_path),
        "BQA_UI_LANGUAGE": "en",
    }
    dependencies = {
        "initial_message": None,
        "status_reader": lambda _root, _values: {},
        "start_action": lambda _root: {"ok": True},
        "restart_action": lambda _root, _values: {"ok": True},
        "stop_action": lambda _root: {"ok": True},
        "stop_confirmation": lambda _root, _translator: False,
        "activity_reader": lambda _limit: [],
        "workspace_log_stream_reader": lambda _last_event_id: iter(()),
    }
    dependencies.update(overrides)
    dashboard = QtDesktopDashboard(
        load_qt_bindings(),
        CLIContext(
            repo_root=tmp_path,
            values=values,
            base_url="http://127.0.0.1:18427",
            token="",
            request_timeout=1.0,
        ),
        **dependencies,
    )
    return application, dashboard


def _wait_until(predicate, application, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        application.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return False


def test_qt_dashboard_composes_the_command_shell(tmp_path):
    from app.cli.desktop_qt.theme import COLORS, build_stylesheet

    application, dashboard = _qt_dashboard(tmp_path)
    try:
        assert dashboard.command_header.objectName() == "commandHeader"
        assert dashboard.command_header.minimumHeight() == 64
        assert dashboard.command_header.maximumHeight() == 64
        assert dashboard.icon_rail.objectName() == "iconRail"
        assert dashboard.icon_rail.minimumWidth() == 76
        assert dashboard.icon_rail.maximumWidth() == 76
        assert dashboard.content_stack is dashboard.stack
        assert dashboard.footer_bar.objectName() == "footerBar"
        assert list(dashboard.navigation_items) == ["runtime", "workspace", "gpt"]
        assert dashboard.navigation_items["runtime"].button.property("active") == "true"
        assert dashboard.navigation_items["workspace"].button.property("active") == "false"
        assert dashboard.navigation_items["gpt"].button.property("active") == "false"
        stylesheet = build_stylesheet()
        assert "QFrame#contentCanvas" in stylesheet
        assert f"background: {COLORS['surface']};" in stylesheet
        assert "QFrame#footerBar" in stylesheet
        assert f"background: {COLORS['panel_raised']};" in stylesheet

        dashboard.navigation_items["runtime"].button.click()
        assert dashboard.content_stack.currentWidget() is dashboard.runtime_panel.widget
        assert dashboard.navigation_items["runtime"].button.property("active") == "true"
        assert dashboard.navigation_items["workspace"].button.property("active") == "false"
        assert dashboard.navigation_items["gpt"].button.property("active") == "false"

        dashboard.navigation_items["workspace"].button.click()
        assert dashboard.content_stack.currentWidget() is dashboard.workspace_logs_panel.widget
        assert dashboard.navigation_items["runtime"].button.property("active") == "false"
        assert dashboard.navigation_items["workspace"].button.property("active") == "true"
        assert dashboard.navigation_items["gpt"].button.property("active") == "false"

        dashboard.navigation_items["gpt"].button.click()
        assert dashboard.content_stack.currentWidget() is dashboard.activity_panel.widget
        assert dashboard.navigation_items["runtime"].button.property("active") == "false"
        assert dashboard.navigation_items["workspace"].button.property("active") == "false"
        assert dashboard.navigation_items["gpt"].button.property("active") == "true"

        dashboard.change_language("Tiếng Việt")
        workspace_label = "Nhật ký Workspace"
        workspace_item = dashboard.navigation_items["workspace"].button
        assert workspace_item.accessibleName() == workspace_label
        assert workspace_item.toolTip() == workspace_label
        assert dashboard.navigation_labels["workspace"].text() == workspace_label
    finally:
        dashboard.close()
        application.processEvents()


def test_qt_dashboard_three_routes_fill_the_desktop_command_shell(tmp_path):
    """The desktop shell keeps every route usable at its supported viewport."""
    from PySide6 import QtCore

    application, dashboard = _qt_dashboard(tmp_path)
    try:
        dashboard.window.resize(1180, 740)
        dashboard.window.show()
        assert _wait_until(dashboard.window.isVisible, application)
        application.processEvents()

        assert dashboard.command_header.height() == 64
        assert dashboard.icon_rail.width() == 76
        assert dashboard.footer_bar.isVisible()
        assert dashboard.footer_bar.height() > 0

        routes = {
            "runtime": dashboard.runtime_panel.widget,
            "workspace": dashboard.workspace_logs_panel.widget,
            "gpt": dashboard.activity_panel.widget,
        }
        for route, page in routes.items():
            dashboard.navigation_items[route].button.click()
            application.processEvents()

            assert dashboard.content_stack.currentWidget() is page
            assert dashboard.navigation_items[route].button.property("active") == "true"
            assert all(
                item.button.property("active") == ("true" if item_route == route else "false")
                for item_route, item in dashboard.navigation_items.items()
            )
            assert dashboard.navigation_items[route].button.accessibleName()
            assert dashboard.navigation_items[route].button.toolTip()
            assert dashboard.navigation_labels[route].isVisible()
            assert page.geometry() == dashboard.content_stack.rect()
            page_rect = QtCore.QRect(
                page.mapTo(dashboard.content_stack, QtCore.QPoint(0, 0)),
                page.size(),
            )
            assert dashboard.content_stack.rect().contains(page_rect)
    finally:
        dashboard.close()
        application.processEvents()


def test_qt_dashboard_refresh_readers_are_off_thread_and_timers_remain_responsive(
    tmp_path,
):
    main_thread = threading.get_ident()
    refresh_threads = queue.Queue()

    def status_reader(_root, _values):
        refresh_threads.put(threading.get_ident())
        return {"workspace": str(tmp_path)}

    application, dashboard = _qt_dashboard(tmp_path, status_reader=status_reader)
    try:
        assert _wait_until(lambda: not refresh_threads.empty(), application)
        assert refresh_threads.get_nowait() != main_thread
        assert dashboard.refresh_timer.interval() == 2_000
        assert dashboard.refresh_timer.isActive()
        assert 0 < dashboard.action_drain_timer.interval() <= 100
        assert dashboard.action_drain_timer.isActive()
    finally:
        dashboard.close()


def test_qt_dashboard_stop_confirmation_and_busy_gate_prevent_overlap(tmp_path):
    action_started = threading.Event()
    action_release = threading.Event()
    confirmation_calls = []
    stop_calls = []

    def start_action(_root):
        action_started.set()
        action_release.wait(timeout=1)
        return {"ok": True}

    def stop_confirmation(root, translator):
        confirmation_calls.append((root, translator.language))
        return True

    application, dashboard = _qt_dashboard(
        tmp_path,
        start_action=start_action,
        stop_action=lambda root: stop_calls.append(root) or {"ok": True},
        stop_confirmation=stop_confirmation,
    )
    try:
        dashboard.start_service()
        assert action_started.wait(timeout=1)
        assert dashboard.busy is True

        dashboard.stop_service()
        dashboard.restart_bridge()

        assert confirmation_calls == []
        assert stop_calls == []
        action_release.set()
        assert _wait_until(lambda: dashboard.busy is False, application)

        dashboard.stop_confirmation = lambda _root, _translator: False
        dashboard.stop_service()
        assert dashboard.busy is False
        assert stop_calls == []

        dashboard.stop_confirmation = stop_confirmation
        dashboard.stop_service()
        assert _wait_until(lambda: dashboard.busy is False and bool(stop_calls), application)
        assert stop_calls == [tmp_path]
        assert len(confirmation_calls) == 1
    finally:
        action_release.set()
        dashboard.close()


def test_qt_dashboard_copy_endpoint_uses_rendered_lifecycle_url(tmp_path):
    endpoint = "https://example.trycloudflare.com/mcp"
    application, dashboard = _qt_dashboard(
        tmp_path,
        status_reader=lambda _root, _values: {"url": endpoint},
    )
    try:
        assert _wait_until(
            lambda: dashboard.latest_status_data is not None, application
        )

        dashboard.copy_endpoint()

        assert application.clipboard().text() == endpoint
    finally:
        dashboard.close()


def test_qt_dashboard_header_keeps_compact_app_name_with_existing_identity(tmp_path):
    application, dashboard = _qt_dashboard(tmp_path)
    try:
        dashboard.window.show()
        application.processEvents()

        assert dashboard.app_name_label.isVisible()
        assert dashboard.app_name_label.text() == "UCS-SecretAgent"
        assert dashboard.identity_label.text() == "UCS // SECRET AGENT"
    finally:
        dashboard.close()


def test_qt_dashboard_refresh_preserves_pending_workspace_until_apply(
    monkeypatch, tmp_path
):
    monkeypatch.delenv("HOST_WORKSPACE_DIR", raising=False)
    monkeypatch.delenv("HOST_DEFAULT_DIR", raising=False)
    pending_workspace = tmp_path / "pending-workspace"
    server_workspace = tmp_path / "server-workspace"
    pending_workspace.mkdir()
    server_workspace.mkdir()
    restart_workspaces = []
    application, dashboard = _qt_dashboard(
        tmp_path,
        restart_action=lambda _root, values: restart_workspaces.append(
            values["HOST_WORKSPACE_DIR"]
        )
        or {"ok": True},
    )
    try:
        assert _wait_until(
            lambda: dashboard.latest_status_data is not None, application
        )
        dashboard.runtime_panel.workspace_value.setText(str(pending_workspace))
        dashboard.workspace_selection_dirty = True

        dashboard._render_status({"workspace": str(server_workspace)})

        assert dashboard.runtime_panel.workspace_value.text() == str(
            pending_workspace
        )
        dashboard.apply_workspace()
        assert _wait_until(lambda: dashboard.busy is False, application)
        assert restart_workspaces == [str(pending_workspace)]
        assert dashboard.ctx.values["HOST_WORKSPACE_DIR"] == str(pending_workspace)
    finally:
        dashboard.close()


def test_qt_dashboard_language_change_preserves_dirty_workspace_for_apply(
    monkeypatch, tmp_path
):
    pending_workspace = tmp_path / "pending-workspace"
    pending_workspace.mkdir()
    restart_workspaces = []
    application, dashboard = _qt_dashboard(
        tmp_path,
        restart_action=lambda _root, values: restart_workspaces.append(
            values["HOST_WORKSPACE_DIR"]
        )
        or {"ok": True},
    )
    monkeypatch.setattr(
        "app.cli.desktop_qt.app.set_desktop_ui_language",
        lambda _root, language: {"BQA_UI_LANGUAGE": language},
    )
    monkeypatch.setattr(
        "app.cli.desktop_qt.app.set_workspace_config",
        lambda _root, workspace: {"HOST_WORKSPACE_DIR": workspace},
    )
    try:
        assert _wait_until(
            lambda: dashboard.latest_status_data is not None, application
        )
        dashboard.runtime_panel.workspace_value.setText(str(pending_workspace))
        dashboard.workspace_selection_dirty = True
        vietnamese = next(
            label
            for label, language in dashboard.language_choices.items()
            if language == "vi"
        )

        dashboard.change_language(vietnamese)

        assert dashboard.workspace_selection_dirty is True
        assert dashboard.runtime_panel.workspace_value.text() == str(pending_workspace)
        dashboard.apply_workspace()
        assert _wait_until(lambda: dashboard.busy is False, application)
        assert restart_workspaces == [str(pending_workspace)]
    finally:
        dashboard.close()


def test_qt_dashboard_busy_workspace_controls_leave_dirty_choice_unmodified(
    monkeypatch, tmp_path
):
    pending_workspace = tmp_path / "pending-workspace"
    pending_workspace.mkdir()
    action_started = threading.Event()
    action_release = threading.Event()
    restart_workspaces = []

    def start_action(_root):
        action_started.set()
        action_release.wait(timeout=1)
        return {"ok": True}

    application, dashboard = _qt_dashboard(
        tmp_path,
        start_action=start_action,
        restart_action=lambda _root, values: restart_workspaces.append(
            values["HOST_WORKSPACE_DIR"]
        )
        or {"ok": True},
    )
    picker_calls = []
    monkeypatch.setattr(
        dashboard.QtWidgets.QFileDialog,
        "getExistingDirectory",
        lambda *_args: picker_calls.append(True) or str(tmp_path / "other"),
    )
    try:
        assert _wait_until(
            lambda: dashboard.latest_status_data is not None, application
        )
        dashboard.runtime_panel.workspace_value.setText(str(pending_workspace))
        dashboard.workspace_selection_dirty = True
        dashboard.start_service()
        assert action_started.wait(timeout=1)

        assert dashboard.runtime_panel.choose_button.isEnabled() is False
        assert dashboard.runtime_panel.apply_button.isEnabled() is False
        dashboard.choose_workspace()
        dashboard.apply_workspace()

        assert picker_calls == []
        assert restart_workspaces == []
        assert dashboard.workspace_selection_dirty is True
        assert dashboard.runtime_panel.workspace_value.text() == str(pending_workspace)
        action_release.set()
        assert _wait_until(lambda: dashboard.busy is False, application)
    finally:
        action_release.set()
        dashboard.close()


def test_qt_dashboard_failed_workspace_apply_keeps_dirty_selection(
    monkeypatch, tmp_path
):
    pending_workspace = tmp_path / "pending-workspace"
    pending_workspace.mkdir()
    action_started = threading.Event()
    action_release = threading.Event()

    def restart_action(_root, _values):
        action_started.set()
        action_release.wait(timeout=1)
        return {"ok": False, "message": "rejected"}

    application, dashboard = _qt_dashboard(
        tmp_path,
        restart_action=restart_action,
    )
    monkeypatch.setattr(
        "app.cli.desktop_qt.app.set_workspace_config",
        lambda _root, workspace: {"HOST_WORKSPACE_DIR": workspace},
    )
    try:
        assert _wait_until(
            lambda: dashboard.latest_status_data is not None, application
        )
        dashboard.runtime_panel.workspace_value.setText(str(pending_workspace))
        dashboard.workspace_selection_dirty = True

        dashboard.apply_workspace()

        assert action_started.wait(timeout=1)
        assert dashboard.workspace_selection_dirty is True
        action_release.set()
        assert _wait_until(lambda: dashboard.busy is False, application)
        assert dashboard.workspace_selection_dirty is True
        assert dashboard.runtime_panel.workspace_value.text() == str(pending_workspace)
    finally:
        action_release.set()
        dashboard.close()
