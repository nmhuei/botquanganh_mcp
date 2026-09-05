import os
import time
from types import SimpleNamespace

import pytest


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def write_image(image, tmp_path, name="qt-render.png"):
    """Persist render evidence only in pytest's temporary directory."""
    target = tmp_path / name
    assert image.save(str(target))
    return target


def count_near_white_pixels(image, excluded_rectangles=()):
    """Count broad near-white areas outside explicitly identified text bounds."""
    def is_near_white(x, y):
        color = image.pixelColor(x, y)
        return color.red() >= 224 and color.green() >= 224 and color.blue() >= 224

    def is_excluded(x, y):
        return any(
            left <= x < left + width and top <= y < top + height
            for left, top, width, height in excluded_rectangles
        )

    count = 0
    for y in range(2, image.height() - 2):
        for x in range(2, image.width() - 2):
            if is_excluded(x, y) or not is_near_white(x, y):
                continue
            if sum(
                is_near_white(sample_x, sample_y)
                for sample_y in range(y - 2, y + 3)
                for sample_x in range(x - 2, x + 3)
            ) >= 21:
                count += 1
    return count


def assert_dark_rectangle(image, rectangle, ceiling=80):
    """Assert a known non-text background rectangle stays below a dark ceiling."""
    left, top, width, height = rectangle
    luminance = []
    for y in range(top, top + height):
        for x in range(left, left + width):
            color = image.pixelColor(x, y)
            luminance.append(
                (color.red() * 299 + color.green() * 587 + color.blue() * 114) // 1000
            )
    assert luminance
    assert max(luminance) <= ceiling


def rectangle_in_fixture(fixture, widget, left, top, width, height):
    from PySide6 import QtCore

    origin = widget.mapTo(fixture.root, QtCore.QPoint(0, 0))
    return (origin.x() + left, origin.y() + top, width, height)


def widget_rectangle_in(widget, ancestor):
    """Return one widget's measured bounds in an ancestor coordinate system."""
    from PySide6 import QtCore

    origin = widget.mapTo(ancestor, QtCore.QPoint(0, 0))
    return (origin.x(), origin.y(), widget.width(), widget.height())


def count_lime_border_pixels(image, rectangle):
    left, top, width, height = rectangle
    count = 0
    for y in range(top, top + height):
        for x in range(left, left + width):
            color = image.pixelColor(x, y)
            if color.red() >= 145 and color.green() >= 225 and color.blue() <= 60:
                count += 1
    return count


def runtime_fixture(*, bridge, server, tunnel):
    """Use only the runtime facts that the presentation layer accepts."""
    return {
        "ok": True,
        "bridge": bridge,
        "server": {"running": server == "running"},
        "tunnel": {"running": tunnel == "running"},
        "url": "https://example.trycloudflare.com/mcp",
        "auth_required": True,
        "workspace": "/work",
    }


def make_runtime_panel(qapp):
    """Render the real Runtime panel inside the shared dark visual system."""
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.runtime import RuntimeCallbacks, RuntimePanel
    from app.cli.desktop_qt.theme import build_stylesheet
    from app.cli.desktop_views.i18n import DesktopTranslator

    root = QtWidgets.QWidget()
    root.setStyleSheet(build_stylesheet())
    layout = QtWidgets.QVBoxLayout(root)
    panel = RuntimePanel(
        QtCore,
        QtWidgets,
        DesktopTranslator("en"),
        RuntimeCallbacks(*(lambda: None for _ in range(7))),
    )
    layout.addWidget(panel.widget)
    root.resize(980, 560)
    root.show()
    qapp.processEvents()
    panel.visual_root = root
    return panel


def make_activity_panel(qapp, tmp_path):
    """Render the real populated Activity panel in the shared dark shell."""
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.activity import QtActivityPanel
    from app.cli.desktop_qt.theme import build_stylesheet

    root = QtWidgets.QWidget()
    root.setObjectName("appRoot")
    root.setStyleSheet(build_stylesheet())
    layout = QtWidgets.QVBoxLayout(root)
    layout.setContentsMargins(8, 8, 8, 8)
    panel = QtActivityPanel(QtCore, QtWidgets, workspace_root=lambda: tmp_path)
    layout.addWidget(panel.widget)
    root.resize(1180, 740)
    root.show()
    qapp.processEvents()
    panel.visual_root = root
    return panel


def activity_sessions_fixture(tmp_path):
    """Provide a dense mix of real session rows for the Activity rail."""
    from app.cli.desktop_views.activity import WorkspaceSession

    return [
        WorkspaceSession(chat_id, tmp_path / chat_id, 10.0 - index)
        for index, chat_id in enumerate(
            (
                "investigation-alpha",
                "security-review",
                "ops-remediation",
                "finance-audit",
                "release-validation",
                "incident-retrospective",
            )
        )
    ]


def activity_records_fixture():
    """Provide dense selected-command history with representative values."""
    commands = (
        ("investigation-alpha", "git status --short", True, 18),
        ("security-review", "python -m pytest tests/security -q", True, 412),
        ("ops-remediation", "systemctl --user status bqa-bridge", False, 96),
        ("finance-audit", "find reports -name '*.json' -maxdepth 3", True, 205),
        ("release-validation", "git diff --check", True, 14),
        ("incident-retrospective", "journalctl --since '30 minutes ago'", True, 731),
        ("investigation-alpha", "rg -n 'workspace_log' app tests", True, 47),
        ("security-review", "python -m pytest tests/strength -x -vv", False, 1_245),
        ("ops-remediation", "bqa ui --help", True, 22),
        ("finance-audit", "git log --oneline -12", True, 31),
    )
    return [
        {
            "event_id": f"activity-visual-{index}",
            "chat_id": chat_id,
            "command": command,
            "ok": ok,
            "timestamp": f"2026-09-02T10:{index:02d}:00+00:00",
            "exit_code": 0 if ok else 1,
            "duration_ms": duration_ms,
            "stdout": f"completed: {command}\nrecord {index}",
            "stderr": "" if ok else "controlled fixture failure",
        }
        for index, (chat_id, command, ok, duration_ms) in enumerate(commands)
    ]


def workspace_events_fixture():
    """Provide dense audit rows spanning status, category, and outcome states."""
    entries = (
        ("host_read_file", "filesystem", "success", "INFO", "visual-chat-a"),
        ("host_write_file", "filesystem", "success", "INFO", "visual-chat-a"),
        ("host_run_command", "process", "failure", "ERROR", "visual-chat-b"),
        ("host_list_directory", "filesystem", "success", "INFO", "visual-chat-c"),
        ("session_open", "session", "success", "INFO", "visual-chat-d"),
        ("host_search", "filesystem", "success", "INFO", "visual-chat-a"),
        ("host_run_command", "process", "success", "INFO", "visual-chat-b"),
        ("session_close", "session", "failure", "WARN", "visual-chat-d"),
        ("host_read_file", "filesystem", "failure", "ERROR", "visual-chat-c"),
        ("host_write_file", "filesystem", "success", "INFO", "visual-chat-a"),
    )
    return tuple(
        {
            "id": f"visual-log-{index}",
            "event": "workspace_log",
            "data": {
                "ts": f"2026-09-02T10:{index:02d}:00+00:00",
                "chat_id": chat_id,
                "event_action": action,
                "event_category": category,
                "event_outcome": outcome,
                "severity_text": severity,
                "event_duration_ms": 12.5 + index,
                "interaction_id": f"interaction-{index}",
                "log_source": "visual-fixture",
                "payload": {
                    "path": f"workspace/item-{index}.json",
                    "offset": index * 8,
                },
            },
        }
        for index, (action, category, outcome, severity, chat_id) in enumerate(entries)
    )


def test_runtime_command_center_uses_metric_strip_detail_cards_and_action_dock(qapp):
    """Catch a regression to sparse cards or a light Runtime native surface."""
    panel = make_runtime_panel(qapp)
    try:
        panel.render(runtime_fixture(bridge="running", server="running", tunnel="running"))
        qapp.processEvents()

        assert panel.metric_strip.objectName() == "runtimeMetricStrip"
        assert len(panel.service_cards) == 3
        assert all(card.detail_row_count == 3 for card in panel.service_cards)
        assert panel.metric_cells[2].label.text() == "Status summary"
        assert [
            card.detail_rows[2].label.text() for card in panel.service_cards
        ] == ["Endpoint", "Status summary", "Status summary"]
        assert [
            card.detail_rows[2].value.text() for card in panel.service_cards
        ] == [
            "https://example.trycloudflare.com/mcp",
            "MCP bridge and Cloudflare tunnel are running.",
            "MCP bridge and Cloudflare tunnel are running.",
        ]
        assert [panel.service_grid.columnStretch(column) for column in range(3)] == [
            1,
            1,
            1,
        ]
        card_widths = [card.widget.width() for card in panel.service_cards]
        assert max(card_widths) - min(card_widths) <= 1
        assert panel.workspace_frame.objectName() == "runtimeWorkspaceFrame"
        assert panel.action_dock.objectName() == "runtimeActionDock"
        panel_layout = panel.widget.layout()
        assert panel_layout.indexOf(panel.workspace_frame) < panel_layout.indexOf(
            panel.action_dock
        )
        assert panel.workspace_frame.geometry().top() < panel.action_dock.geometry().top()
        assert panel.start_button.property("variant") == "primary"
        assert panel.stop_button.property("variant") == "danger"
        image = panel.widget.grab().toImage()
        assert count_near_white_pixels(
            image,
            (widget_rectangle_in(panel.page_title_label, panel.widget),),
        ) == 0
    finally:
        panel.visual_root.close()
        qapp.processEvents()


def test_activity_workbench_renders_dark_session_command_and_inspection_surfaces(qapp, tmp_path):
    """Catch regressions to an unframed rail, light inspector, or mouse-only toggles."""
    panel = make_activity_panel(qapp, tmp_path)
    try:
        sessions = activity_sessions_fixture(tmp_path)
        panel.refresh(sessions, activity_records_fixture())
        for session in sessions:
            panel.reveal_session(session.chat_id)
        panel.show_all_sessions()
        panel.command_table.selectRow(0)
        qapp.processEvents()
        image = panel.widget.grab().toImage()
        write_image(image, tmp_path, "populated-activity-workbench.png")

        assert panel.session_model.rowCount() == 6
        assert panel.session_rail.minimumWidth() == 260
        assert panel.command_toolbar.objectName() == "activityCommandToolbar"
        assert panel.investigation_splitter.orientation() == panel.QtCore.Qt.Horizontal
        assert panel.inspector_frame.objectName() == "inspectorSurface"
        assert count_near_white_pixels(
            image,
            (widget_rectangle_in(panel.page_title_label, panel.widget),),
        ) == 0
        assert panel.input_toggle.focusPolicy() != panel.QtCore.Qt.NoFocus
        assert panel.output_toggle.focusPolicy() != panel.QtCore.Qt.NoFocus
    finally:
        panel.visual_root.close()
        qapp.processEvents()


def make_native_control_fixture(qapp):
    """Render only native Qt controls; no dashboard behavior or backend state."""
    from PySide6 import QtCore, QtWidgets
    from app.cli.desktop_qt.theme import build_stylesheet

    root = QtWidgets.QWidget()
    root.setStyleSheet(build_stylesheet())
    layout = QtWidgets.QVBoxLayout(root)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(8)

    tabs = QtWidgets.QTabWidget()
    plain_editor = QtWidgets.QPlainTextEdit()
    rich_editor = QtWidgets.QTextEdit()
    plain_editor.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
    rich_editor.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
    for editor in (plain_editor, rich_editor):
        editor.setPlainText(
            "wide viewport " + "x" * 180 + "\n" + "\n".join(
                f"line {index}" for index in range(60)
            )
        )
        editor.setMinimumSize(250, 110)
    tabs.addTab(plain_editor, "Plain")
    tabs.addTab(rich_editor, "Rich")
    layout.addWidget(tabs)

    splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
    splitter.setHandleWidth(10)
    splitter.addWidget(QtWidgets.QLabel("left"))
    splitter.addWidget(QtWidgets.QLabel("right"))
    splitter.setSizes((160, 160))
    layout.addWidget(splitter)

    combo = QtWidgets.QComboBox()
    combo.addItems(("One", "Two", "Three"))
    layout.addWidget(combo)
    focus_button = QtWidgets.QPushButton("Focus ring")
    layout.addWidget(focus_button)

    root.resize(420, 430)
    root.show()
    qapp.processEvents()
    plain_editor.verticalScrollBar().setValue(8)
    plain_editor.horizontalScrollBar().setValue(8)
    qapp.processEvents()
    return SimpleNamespace(
        root=root,
        tabs=tabs,
        plain_editor=plain_editor,
        rich_editor=rich_editor,
        splitter=splitter,
        combo=combo,
        focus_button=focus_button,
    )


def make_populated_dashboard(qapp, tmp_path):
    """Build the real dashboard with a deterministic injected log stream."""
    from app.cli.context import CLIContext
    from app.cli.desktop_qt.app import QtDesktopDashboard
    from app.cli.desktop_qt.compat import load_qt_bindings

    events = workspace_events_fixture()
    delivered = False

    def stream_reader(_last_event_id):
        nonlocal delivered
        if delivered:
            return iter(())
        delivered = True
        return iter(events)

    dashboard = QtDesktopDashboard(
        load_qt_bindings(),
        CLIContext(
            repo_root=tmp_path,
            values={
                "HOST_CHAT_ROOT": str(tmp_path / "chats"),
                "HOST_WORKSPACE_DIR": str(tmp_path),
                "BQA_UI_LANGUAGE": "en",
            },
            base_url="http://127.0.0.1:18427",
            token="",
            request_timeout=1.0,
        ),
        initial_message=None,
        status_reader=lambda _root, _values: runtime_fixture(
            bridge="running", server="running", tunnel="running"
        ),
        start_action=lambda _root: {"ok": True},
        restart_action=lambda _root, _values: {"ok": True},
        stop_action=lambda _root: {"ok": True},
        stop_confirmation=lambda _root, _translator: False,
        activity_reader=lambda _limit: activity_records_fixture(),
        workspace_log_stream_reader=stream_reader,
    )
    # The visual fixture controls its own deterministic snapshot. Keep the
    # dashboard's initial read, but prevent the periodic refresh from replacing
    # the injected session rows while the three routes are being captured.
    dashboard.refresh_timer.stop()
    dashboard.window.resize(1180, 740)
    dashboard.window.show()
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        qapp.processEvents()
        if (
            len(dashboard.workspace_logs_panel.state.rows) == len(events)
            and dashboard.runtime_panel.latest_data is not None
            and dashboard.activity_panel.command_model.rowCount() > 0
            and not dashboard.refresh_busy
        ):
            break
        time.sleep(0.005)
    sessions = activity_sessions_fixture(tmp_path)
    dashboard.activity_panel.refresh(sessions, activity_records_fixture())
    for session in sessions:
        dashboard.activity_panel.reveal_session(session.chat_id)
    dashboard.activity_panel.show_all_sessions()
    dashboard.activity_panel.command_table.selectRow(0)
    dashboard.language_combo.clearFocus()
    dashboard.window.setFocus()
    qapp.processEvents()
    assert len(dashboard.workspace_logs_panel.state.rows) == len(events)
    assert dashboard.runtime_panel.latest_data is not None
    assert dashboard.activity_panel.session_model.rowCount() == len(sessions)
    assert dashboard.activity_panel.command_model.rowCount() == len(
        activity_records_fixture()
    )
    return dashboard


def assert_widget_fits_inside(widget, container):
    """Reject a visible surface that is clipped by its intended container."""
    from PySide6 import QtCore

    top_left = widget.mapTo(container, QtCore.QPoint(0, 0))
    mapped = QtCore.QRect(top_left, widget.size())
    assert mapped.isValid(), f"invalid geometry for {widget.objectName()!r}: {mapped}"
    assert container.rect().contains(mapped), (
        f"{widget.objectName()!r} escapes {container.objectName()!r}: "
        f"child={mapped}, container={container.rect()}"
    )


def assert_vertical_surfaces_do_not_overlap(*widgets):
    """Reject stacked shell surfaces that paint over one another."""
    from PySide6 import QtCore

    ancestor = widgets[0].window()
    rectangles = [
        QtCore.QRect(widget.mapTo(ancestor, QtCore.QPoint(0, 0)), widget.size())
        for widget in widgets
    ]
    for upper, upper_rect, lower, lower_rect in zip(
        widgets, rectangles, widgets[1:], rectangles[1:]
    ):
        assert upper_rect.bottom() < lower_rect.top(), (
            f"{upper.objectName()!r} overlaps {lower.objectName()!r}: "
            f"upper={upper_rect}, lower={lower_rect}"
        )


def assert_table_headers_fit_without_horizontal_scroll(table):
    """Prove every translated table header fits the fixed visual viewport."""
    from PySide6 import QtCore

    header = table.horizontalHeader()
    model = table.model()
    assert table.horizontalScrollBar().maximum() == 0
    for section in range(model.columnCount()):
        label = str(
            model.headerData(
                section, QtCore.Qt.Horizontal, QtCore.Qt.DisplayRole
            )
            or ""
        )
        assert header.fontMetrics().horizontalAdvance(label) + 16 <= header.sectionSize(
            section
        ), f"elided header {label!r} in section {section}"
    last = model.columnCount() - 1
    assert (
        header.sectionViewportPosition(last) + header.sectionSize(last)
        <= table.viewport().width()
    )


def assert_table_cell_exposes_full_text(table, row, column, expected):
    """Require a fitting full display value or an exact full-value tooltip."""
    from PySide6 import QtCore

    index = table.model().index(row, column)
    displayed = str(table.model().data(index, QtCore.Qt.DisplayRole) or "")
    tooltip = str(table.model().data(index, QtCore.Qt.ToolTipRole) or "")
    available = max(0, table.visualRect(index).width() - 16)
    display_fits = (
        displayed == expected
        and table.fontMetrics().horizontalAdvance(displayed) <= available
    )
    assert display_fits or tooltip == expected, (
        f"cell ({row}, {column}) hides {expected!r}: "
        f"display={displayed!r}, tooltip={tooltip!r}, available={available}px"
    )


def assert_table_cell_displays_full_text(table, row, column, expected):
    """Require a short operational value to render without visual elision."""
    from PySide6 import QtCore, QtWidgets

    index = table.model().index(row, column)
    displayed = str(table.model().data(index, QtCore.Qt.DisplayRole) or "")
    option = QtWidgets.QStyleOptionViewItem()
    table.initViewItemOption(option)
    required = table.itemDelegateForIndex(index).sizeHint(option, index).width()
    available = table.visualRect(index).width()
    assert displayed == expected
    assert required <= available, (
        f"cell ({row}, {column}) visually elides {expected!r}: "
        f"required={required}px, available={available}px"
    )


def test_full_shell_and_route_compositions_match_the_goal_geometry(qapp, tmp_path):
    """Reject generic inset shell/page compositions even when they are merely dark."""
    from PySide6 import QtCore
    from app.cli.desktop_qt.theme import COLORS, build_stylesheet

    dashboard = make_populated_dashboard(qapp, tmp_path)
    try:
        root = dashboard.window.centralWidget()
        assert hasattr(dashboard, "body_frame")
        assert dashboard.command_header.geometry() == QtCore.QRect(0, 0, 1180, 64)
        assert dashboard.footer_bar.geometry().left() == 0
        assert dashboard.footer_bar.geometry().right() == root.width() - 1
        assert dashboard.footer_bar.geometry().bottom() == root.height() - 1
        assert dashboard.icon_rail.geometry().left() == 0
        assert dashboard.content_canvas.geometry().right() == root.width() - 1
        assert (
            dashboard.icon_rail.geometry().right() + 1
            == dashboard.content_canvas.geometry().left()
        )
        assert dashboard.header_brand.logo.pixmap().width() >= 44
        assert all(
            not navigation.button.text() and not navigation.button.icon().isNull()
            for navigation in dashboard.navigation_items.values()
        )

        style = build_stylesheet()
        assert "QFrame#runtimeMetricStrip" in style
        assert "QFrame#runtimeActionDock" in style
        assert f"background: {COLORS['danger']};" in style
        page_title_rule = style.split('QLabel[role="pageTitle"]', 1)[1].split(
            "}", 1
        )[0]
        assert f"color: {COLORS['text']};" in page_title_rule

        dashboard._show_page("runtime")
        qapp.processEvents()
        runtime = dashboard.runtime_panel
        assert hasattr(runtime, "page_title_label")
        assert hasattr(runtime, "page_subtitle_label")
        assert runtime.page_title_label.isVisible()
        assert runtime.page_subtitle_label.isVisible()
        assert runtime.page_title_label.height() >= 24
        assert runtime.metric_strip.width() >= runtime.widget.width() * 0.95
        assert runtime.metric_strip.height() >= 92
        assert runtime.endpoint_value.wordWrap() is False
        assert len(runtime.service_icon_labels) == 3
        assert all(not label.pixmap().isNull() for label in runtime.service_icon_labels)
        assert runtime.stop_button.property("variant") == "danger"

        dashboard._show_page("workspace")
        qapp.processEvents()
        logs = dashboard.workspace_logs_panel
        assert hasattr(logs, "page_title_label")
        assert hasattr(logs, "page_subtitle_label")
        assert logs.page_title_label.isVisible()
        assert logs.page_subtitle_label.isVisible()
        assert logs.toolbar_frame.height() <= 52
        assert logs.model.rowCount() == 10
        assert_table_headers_fit_without_horizontal_scroll(logs.table)
        table_size, inspector_size = logs.content_splitter.sizes()
        assert table_size / (table_size + inspector_size) >= 0.66
        assert hasattr(logs, "inspector_detail_grid")
        assert logs.inspector_detail_grid.isVisible()

        dashboard._show_page("gpt")
        qapp.processEvents()
        activity = dashboard.activity_panel
        assert hasattr(activity, "page_title_label")
        assert hasattr(activity, "page_subtitle_label")
        assert activity.page_title_label.isVisible()
        assert activity.page_subtitle_label.isVisible()
        assert activity.session_model.rowCount() == 6
        assert activity.command_model.rowCount() == 10
        assert activity.investigation_splitter.orientation() == QtCore.Qt.Horizontal
        assert hasattr(activity, "command_input_view")
        assert activity.command_input_view.toPlainText()
        assert_table_headers_fit_without_horizontal_scroll(activity.sessions_table)
        assert_table_headers_fit_without_horizontal_scroll(activity.command_table)
        expected_session_rows = (
            ("investigation-alpha", "enabled", "00:00:10"),
            ("security-review", "enabled", "00:00:09"),
            ("ops-remediation", "enabled", "00:00:08"),
            ("finance-audit", "enabled", "00:00:07"),
            ("release-validation", "enabled", "00:00:06"),
            ("incident-retrospective", "enabled", "00:00:05"),
        )
        for row, expected_values in enumerate(expected_session_rows):
            for column, expected in enumerate(expected_values):
                assert_table_cell_exposes_full_text(
                    activity.sessions_table, row, column, expected
                )
            assert_table_cell_displays_full_text(
                activity.sessions_table, row, 1, expected_values[1]
            )
            assert_table_cell_displays_full_text(
                activity.sessions_table, row, 2, expected_values[2]
            )
        assert (
            activity.input_panel.width()
            >= activity.investigation_splitter.width() * 0.35
        )
        assert (
            activity.output_panel.width()
            >= activity.investigation_splitter.width() * 0.35
        )
        assert dashboard.language_combo.hasFocus() is False
    finally:
        dashboard.close()
        qapp.processEvents()


def test_fullscreen_gpt_activity_keeps_inspectors_in_the_primary_work_area(
    qapp, tmp_path
):
    """Fullscreen must grow the workbench, not an empty title region."""
    dashboard = make_populated_dashboard(qapp, tmp_path)
    try:
        dashboard._show_page("gpt")
        dashboard.window.resize(1920, 1080)
        dashboard.window.show()
        qapp.processEvents()

        activity = dashboard.activity_panel
        command_height = activity.command_frame.height()
        inspection_height = activity.inspection_workspace.height()

        assert activity.page_heading.height() <= 64
        assert command_height <= 260
        assert inspection_height >= command_height * 1.8
    finally:
        dashboard.close()
        qapp.processEvents()


def test_navigation_icons_render_centered_over_their_route_labels(qapp, tmp_path):
    """The painted route marks must not drift right when the rail clips a button."""
    dashboard = make_populated_dashboard(qapp, tmp_path)
    try:
        image = dashboard.window.grab().toImage()
        for route, navigation in dashboard.navigation_items.items():
            button = navigation.button
            label = dashboard.navigation_labels[route]
            button_origin = button.mapTo(dashboard.window, button.rect().topLeft())
            label_origin = label.mapTo(dashboard.window, label.rect().topLeft())
            icon_pixels = []
            for y in range(button_origin.y(), button_origin.y() + button.height()):
                for x in range(button_origin.x() + 4, button_origin.x() + button.width()):
                    color = image.pixelColor(x, y)
                    if color.red() >= 145 and color.green() >= 220 and color.blue() <= 80:
                        icon_pixels.append(x)
            assert icon_pixels, f"{route} icon was not rendered"
            icon_center = sum(icon_pixels) / len(icon_pixels)
            label_center = label_origin.x() + (label.width() - 1) / 2
            assert abs(icon_center - label_center) <= 1.0, (
                f"{route} icon center {icon_center:.2f} differs from label center "
                f"{label_center:.2f}"
            )
    finally:
        dashboard.close()
        qapp.processEvents()


def test_all_populated_routes_fit_the_ucs_visual_frame_at_1180x740(qapp, tmp_path):
    """Catch shell growth, clipping, overlap, or light native route surfaces."""
    dashboard = make_populated_dashboard(qapp, tmp_path)
    try:
        dashboard.window.resize(1180, 740)
        dashboard.window.show()
        qapp.processEvents()

        route_contracts = {
            "runtime": (
                "runtime.png",
                (
                    dashboard.runtime_panel.page_heading.widget,
                    dashboard.runtime_panel.metric_strip,
                    *(
                        card.widget
                        for card in dashboard.runtime_panel.service_cards
                    ),
                    dashboard.runtime_panel.workspace_frame,
                    dashboard.runtime_panel.action_dock,
                ),
            ),
            "workspace": (
                "workspace.png",
                (
                    dashboard.workspace_logs_panel.page_heading.widget,
                    dashboard.workspace_logs_panel.toolbar_frame,
                    dashboard.workspace_logs_panel.table_frame,
                    dashboard.workspace_logs_panel.inspector_frame,
                ),
            ),
            "gpt": (
                "activity.png",
                (
                    dashboard.activity_panel.session_rail,
                    dashboard.activity_panel.command_toolbar,
                    dashboard.activity_panel.investigation_controls,
                    dashboard.activity_panel.command_frame,
                    dashboard.activity_panel.inspector_frame,
                ),
            ),
        }

        assert (dashboard.window.width(), dashboard.window.height()) == (1180, 740)
        assert dashboard.activity_panel.session_model.rowCount() > 0
        assert_vertical_surfaces_do_not_overlap(
            dashboard.command_header,
            dashboard.content_canvas,
            dashboard.footer_bar,
        )
        for route, (artifact_name, surfaces) in route_contracts.items():
            dashboard._show_page(route)
            qapp.processEvents()
            if route == "gpt":
                assert dashboard.activity_panel.session_model.rowCount() == len(
                    activity_sessions_fixture(tmp_path)
                )
                assert dashboard.activity_panel.command_model.rowCount() == len(
                    activity_records_fixture()
                )
            page = dashboard.content_stack.currentWidget()
            captured_image = dashboard.window.grab().toImage()
            artifact_path = write_image(captured_image, tmp_path, artifact_name)
            image = dashboard.QtGui.QImage(str(artifact_path))

            assert image.width() == 1180
            assert image.height() == 740
            page_title_label = {
                "runtime": dashboard.runtime_panel.page_title_label,
                "workspace": dashboard.workspace_logs_panel.page_title_label,
                "gpt": dashboard.activity_panel.page_title_label,
            }[route]
            assert count_near_white_pixels(
                image,
                (widget_rectangle_in(page_title_label, dashboard.window),),
            ) == 0
            assert dashboard.command_header.height() == 64
            assert dashboard.icon_rail.width() == 76
            assert dashboard.footer_bar.isVisible()
            assert page.geometry().isValid()
            assert page.geometry() == dashboard.content_stack.rect()
            assert_widget_fits_inside(page, dashboard.content_stack)
            for surface in surfaces:
                assert surface.isVisible()
                assert_widget_fits_inside(surface, page)
    finally:
        dashboard.close()
        qapp.processEvents()


def test_visual_system_styles_all_native_inspection_controls(qapp):
    from app.cli.desktop_qt.theme import build_stylesheet

    style = build_stylesheet()
    for selector in (
        "QTabWidget::pane", "QTabBar::tab", "QTextEdit", "QPlainTextEdit",
        "QScrollBar:vertical", "QScrollBar:horizontal", "QSplitter::handle",
        "QToolTip", "QComboBox QAbstractItemView", "QAbstractScrollArea::corner",
        "QHeaderView", "QTableCornerButton::section",
    ):
        assert selector in style


def test_populated_logs_inspector_has_no_light_native_surface(qapp, tmp_path):
    dashboard = make_populated_dashboard(qapp, tmp_path)
    try:
        dashboard._show_page("workspace")
        dashboard.workspace_logs_panel.table.selectRow(0)
        qapp.processEvents()
        panel = dashboard.workspace_logs_panel
        image = panel.inspector_frame.grab().toImage()
        write_image(image, tmp_path, "populated-workspace-inspector-frame.png")

        assert panel.toolbar_frame.objectName() == "denseToolbar"
        assert panel.inspector_frame.objectName() == "workspaceLogsInspectorFrame"
        assert panel.inspector_frame.property("role") == "inspectorSurface"
        assert panel.content_splitter.sizes()[0] > panel.content_splitter.sizes()[1]
        assert panel.event_count_label.text()
        assert count_near_white_pixels(image) == 0
    finally:
        dashboard.close()
        qapp.processEvents()


def test_native_controls_render_dark_known_surface_rectangles(qapp, tmp_path):
    fixture = make_native_control_fixture(qapp)
    try:
        fixture.tabs.setCurrentIndex(0)
        qapp.processEvents()
        plain_image = fixture.root.grab().toImage()
        write_image(plain_image, tmp_path, "native-controls-plain.png")

        assert fixture.plain_editor.verticalScrollBar().isVisible()
        assert fixture.plain_editor.horizontalScrollBar().isVisible()
        assert_dark_rectangle(
            plain_image,
            rectangle_in_fixture(fixture, fixture.plain_editor.viewport(), 180, 78, 28, 20),
        )
        assert_dark_rectangle(
            plain_image,
            rectangle_in_fixture(fixture, fixture.plain_editor.verticalScrollBar(), 2, 70, 4, 16),
        )
        assert_dark_rectangle(
            plain_image,
            rectangle_in_fixture(fixture, fixture.plain_editor.horizontalScrollBar(), 70, 2, 16, 4),
        )
        vertical_bar = fixture.plain_editor.verticalScrollBar()
        horizontal_bar = fixture.plain_editor.horizontalScrollBar()
        corner = vertical_bar.mapTo(fixture.root, vertical_bar.rect().topLeft())
        horizontal_corner = horizontal_bar.mapTo(fixture.root, horizontal_bar.rect().topLeft())
        assert_dark_rectangle(
            plain_image,
            (corner.x() + 2, horizontal_corner.y() + 2, 4, 4),
        )
        assert_dark_rectangle(
            plain_image,
            rectangle_in_fixture(fixture, fixture.splitter.handle(1), 2, 2, 4, 10),
        )
        first_tab = fixture.tabs.tabBar().tabRect(0)
        second_tab = fixture.tabs.tabBar().tabRect(1)
        tab_origin = fixture.tabs.tabBar().mapTo(fixture.root, first_tab.topLeft())
        assert_dark_rectangle(
            plain_image,
            (tab_origin.x() + first_tab.width() - 12, tab_origin.y() + 8, 6, 8),
        )
        tab_origin = fixture.tabs.tabBar().mapTo(fixture.root, second_tab.topLeft())
        assert_dark_rectangle(
            plain_image,
            (tab_origin.x() + second_tab.width() - 12, tab_origin.y() + 8, 6, 8),
        )

        fixture.tabs.setCurrentIndex(1)
        qapp.processEvents()
        rich_image = fixture.root.grab().toImage()
        write_image(rich_image, tmp_path, "native-controls-rich.png")
        assert_dark_rectangle(
            rich_image,
            rectangle_in_fixture(fixture, fixture.rich_editor.viewport(), 180, 78, 28, 20),
        )

        fixture.combo.showPopup()
        qapp.processEvents()
        assert fixture.combo.view().isVisible()
        combo_image = fixture.combo.view().grab().toImage()
        write_image(combo_image, tmp_path, "native-controls-combo-popup.png")
        viewport = fixture.combo.view().viewport().geometry()
        assert_dark_rectangle(combo_image, (viewport.x() + 80, viewport.y() + 40, 20, 16))
    finally:
        fixture.combo.hidePopup()
        fixture.root.close()
        qapp.processEvents()


def test_native_focus_ring_is_rendered_on_button_border(qapp, tmp_path):
    fixture = make_native_control_fixture(qapp)
    try:
        fixture.plain_editor.setFocus()
        qapp.processEvents()
        unfocused_image = fixture.root.grab().toImage()
        write_image(unfocused_image, tmp_path, "native-focus-ring-unfocused.png")

        fixture.focus_button.setFocus()
        qapp.processEvents()
        focused_image = fixture.root.grab().toImage()
        write_image(focused_image, tmp_path, "native-focus-ring-focused.png")
        border = rectangle_in_fixture(
            fixture,
            fixture.focus_button,
            0,
            0,
            fixture.focus_button.width(),
            fixture.focus_button.height(),
        )
        left, top, width, height = border
        edge_strips = (
            (left + 8, top, width - 16, 2),
            (left + 8, top + height - 2, width - 16, 2),
            (left, top + 8, 2, height - 16),
            (left + width - 2, top + 8, 2, height - 16),
        )
        unfocused_counts = [
            count_lime_border_pixels(unfocused_image, edge) for edge in edge_strips
        ]
        focused_counts = [
            count_lime_border_pixels(focused_image, edge) for edge in edge_strips
        ]
        required_edge_counts = (width - 16, width - 16, height - 16, height - 16)

        assert unfocused_counts == [0, 0, 0, 0]
        assert all(
            count >= required
            for count, required in zip(focused_counts, required_edge_counts)
        )
    finally:
        fixture.root.close()
        qapp.processEvents()
