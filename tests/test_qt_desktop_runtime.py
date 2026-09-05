import os

import pytest


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def test_runtime_panel_renders_ready_state(qapp):
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.runtime import RuntimeCallbacks, RuntimePanel
    from app.cli.desktop_views.i18n import DesktopTranslator

    callbacks = RuntimeCallbacks(
        copy_endpoint=lambda: None,
        choose_workspace=lambda: None,
        apply_workspace=lambda: None,
        start=lambda: None,
        stop=lambda: None,
        restart=lambda: None,
        refresh=lambda: None,
    )
    panel = RuntimePanel(QtCore, QtWidgets, DesktopTranslator("en"), callbacks)
    panel.render(
        {
            "ok": True,
            "bridge": "ready",
            "server": {"running": True, "pid": 123},
            "tunnel": {"running": True},
            "url": "https://example.trycloudflare.com/mcp",
            "auth_required": True,
            "workspace": "/work",
        }
    )

    assert panel.status_label.text() == "Ready"
    assert "https://example.trycloudflare.com/mcp" in panel.endpoint_value.text()
    assert panel.bridge_value.text() == "ready"
    assert panel.server_value.text() == "running"
    assert panel.tunnel_value.text() == "running"


def test_runtime_panel_exposes_command_center_layout_contract(qapp):
    """Catch localized display text leaking into command-center pill states."""
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.runtime import RuntimeCallbacks, RuntimePanel
    from app.cli.desktop_qt.theme import build_stylesheet
    from app.cli.desktop_views.i18n import DesktopTranslator

    panel = RuntimePanel(
        QtCore,
        QtWidgets,
        DesktopTranslator("vi"),
        RuntimeCallbacks(*(lambda: None for _ in range(7))),
    )

    assert panel.metric_strip.objectName() == "runtimeMetricStrip"
    assert len(panel.metric_cells) == 3
    assert isinstance(panel.service_grid, QtWidgets.QGridLayout)
    assert panel.workspace_frame.objectName() == "runtimeWorkspaceFrame"
    assert panel.action_dock.objectName() == "runtimeActionDock"
    assert (
        panel.service_grid.count()
        == len(panel.service_cards)
        == len(panel.service_pills)
        == 3
    )
    assert all(card.detail_row_count == 3 for card in panel.service_cards)
    assert [panel.service_grid.columnStretch(column) for column in range(3)] == [1, 1, 1]
    assert [
        panel.service_grid.itemAtPosition(0, column).widget()
        for column in range(3)
    ] == [card.widget for card in panel.service_cards]
    assert panel.start_button.property("variant") == "primary"
    assert panel.stop_button.property("variant") == "danger"
    for name, button in (
        ("runtimeStartButton", panel.start_button),
        ("runtimeRefreshButton", panel.refresh_button),
        ("runtimeRestartButton", panel.restart_button),
        ("runtimeStopButton", panel.stop_button),
    ):
        assert panel.widget.findChild(QtWidgets.QPushButton, name) is button
    for data, health_state, service_states in (
        (
            {
                "ok": True,
                "bridge": "ready",
                "server": {"running": True},
                "tunnel": {"running": True},
            },
            "ready",
            ["ready", "ready", "ready"],
        ),
        (
            {
                "ok": False,
                "bridge": "stopped",
                "server": {"running": False},
                "tunnel": {"running": False},
            },
            "stopped",
            ["stopped", "stopped", "stopped"],
        ),
        (
            {
                "ok": False,
                "bridge": "warning",
                "server": {"running": True},
                "tunnel": {"running": False},
            },
            "warning",
            ["warning", "ready", "stopped"],
        ),
    ):
        panel.render(data)
        assert panel.status_pill.widget.property("state") == health_state
        assert [
            pill.widget.property("state") for pill in panel.service_pills
        ] == service_states
    stylesheet = build_stylesheet()
    for state in ("ready", "warning", "stopped"):
        assert f'QLabel[role="pill"][state="{state}"]' in stylesheet


def test_runtime_panel_busy_disables_actions(qapp):
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.runtime import RuntimeCallbacks, RuntimePanel
    from app.cli.desktop_views.i18n import DesktopTranslator

    panel = RuntimePanel(
        QtCore,
        QtWidgets,
        DesktopTranslator("en"),
        RuntimeCallbacks(*(lambda: None for _ in range(7))),
    )
    panel.set_busy(True)

    assert panel.start_button.isEnabled() is False
    assert panel.stop_button.isEnabled() is False
    assert panel.restart_button.isEnabled() is False
    assert panel.refresh_button.isEnabled() is False
    assert panel.choose_button.isEnabled() is False
    assert panel.apply_button.isEnabled() is False


def test_runtime_panel_translator_refreshes_initial_runtime_text(qapp):
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.runtime import RuntimeCallbacks, RuntimePanel
    from app.cli.desktop_views.i18n import DesktopTranslator

    translator = DesktopTranslator("vi")
    panel = RuntimePanel(
        QtCore,
        QtWidgets,
        DesktopTranslator("en"),
        RuntimeCallbacks(*(lambda: None for _ in range(7))),
    )
    panel.set_translator(translator)

    assert [card.title.text() for card in panel.service_cards] == [
        translator.text("field.mcp_bridge"),
        translator.text("field.server"),
        translator.text("field.tunnel"),
    ]
    assert panel.status_label.text() == translator.text("status.loading")
    assert panel.endpoint_value.text() == translator.text("status.not_available")
    assert panel.bridge_value.text() == translator.text("status.not_available")
    assert panel.server_value.text() == translator.text("status.not_available")
    assert panel.tunnel_value.text() == translator.text("status.not_available")
