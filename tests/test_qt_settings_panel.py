"""Tests for the QtSettingsPanel and Theme/Language switching."""

from __future__ import annotations

import pytest
from PySide6 import QtCore, QtWidgets

from app.cli.desktop_qt.settings import QtSettingsPanel
from app.cli.desktop_qt.theme import build_stylesheet, get_theme_colors
from app.cli.desktop_views.i18n import DesktopTranslator


import os

@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


def test_theme_colors_and_stylesheet_generation():
    dark_colors = get_theme_colors("dark")
    light_colors = get_theme_colors("light")
    assert dark_colors["canvas"] == "#090d0c"
    assert light_colors["canvas"] == "#f4f6f8"

    dark_style = build_stylesheet("dark")
    light_style = build_stylesheet("light")
    assert "#090d0c" in dark_style
    assert "#f4f6f8" in light_style
    assert "settingsPage" in dark_style
    assert "settingsPage" in light_style


def test_qt_settings_panel_builds_and_toggles_theme_and_language(qapp):
    translator = DesktopTranslator("vi")
    theme_calls = []
    lang_calls = []

    panel = QtSettingsPanel(
        QtCore,
        QtWidgets,
        translator,
        current_theme="dark",
        on_change_language=lambda lang: lang_calls.append(lang),
        on_change_theme=lambda theme: theme_calls.append(theme),
        get_workspace=lambda: "/home/undertaker/workspace",
    )

    assert panel.widget.objectName() == "settingsPage"
    assert panel.current_theme == "dark"
    assert "CÀI ĐẶT" in panel.heading.title_label.text()
    assert panel.dark_button.property("variant") == "primary"
    assert panel.light_button.property("variant") == "secondary"
    assert panel.vi_button.property("variant") == "primary"
    assert panel.en_button.property("variant") == "secondary"

    # Click light button
    panel.light_button.click()
    assert theme_calls == ["light"]
    assert panel.current_theme == "light"
    assert panel.light_button.property("variant") == "primary"
    assert panel.dark_button.property("variant") == "secondary"

    # Click English button
    panel.en_button.click()
    assert lang_calls == ["en"]

    # Switch translator to English
    en_translator = DesktopTranslator("en")
    panel.set_translator(en_translator)
    assert "SETTINGS" in panel.heading.title_label.text()
    assert "Theme & Appearance" in panel.theme_heading.text()
    assert "Language" in panel.lang_heading.text()


def test_all_12_developer_themes_available_and_generate_valid_stylesheets():
    from app.cli.desktop_qt.theme import list_available_themes

    themes = list_available_themes()
    assert len(themes) >= 10, f"Expected at least 10 themes, found {len(themes)}"

    expected_ids = {
        "dark",
        "light",
        "dracula",
        "one_dark",
        "monokai",
        "nord",
        "tokyo_night",
        "gruvbox",
        "catppuccin",
        "synthwave",
        "solarized_dark",
        "github_dark",
    }
    actual_ids = {t["id"] for t in themes}
    assert expected_ids.issubset(actual_ids)

    required_tokens = {
        "canvas",
        "panel",
        "surface",
        "surface_2",
        "surface_3",
        "graphite_deep",
        "graphite_inset",
        "graphite_mid",
        "graphite_raised",
        "panel_raised",
        "border_subtle",
        "border",
        "border_strong",
        "text",
        "muted",
        "subtle",
        "lime",
        "success",
        "warning",
        "danger",
    }

    for theme_info in themes:
        theme_id = theme_info["id"]
        colors = get_theme_colors(theme_id)
        assert required_tokens.issubset(colors.keys()), f"Missing tokens in theme {theme_id}"

        # Verify hex color format
        for token, hex_code in colors.items():
            assert hex_code.startswith("#"), f"Invalid hex color for {token} in {theme_id}: {hex_code}"

        # Verify stylesheet builds cleanly
        style = build_stylesheet(theme_id)
        assert colors["canvas"] in style
        assert "settingsPage" in style


def test_qt_settings_panel_supports_switching_all_themes(qapp):
    translator = DesktopTranslator("vi")
    theme_calls = []

    panel = QtSettingsPanel(
        QtCore,
        QtWidgets,
        translator,
        current_theme="dark",
        on_change_theme=lambda theme: theme_calls.append(theme),
    )

    assert len(panel.theme_buttons) >= 10

    # Test clicking Dracula
    dracula_btn = panel.theme_buttons["dracula"]
    dracula_btn.click()
    assert theme_calls[-1] == "dracula"
    assert panel.current_theme == "dracula"
    assert dracula_btn.property("variant") == "primary"
    assert panel.dark_button.property("variant") == "secondary"
    assert panel.light_button.property("variant") == "secondary"
    assert "Dracula" in panel.metric_theme.value.text()

    # Test clicking Nord
    nord_btn = panel.theme_buttons["nord"]
    nord_btn.click()
    assert theme_calls[-1] == "nord"
    assert panel.current_theme == "nord"
    assert nord_btn.property("variant") == "primary"
    assert dracula_btn.property("variant") == "secondary"
    assert "Nord" in panel.metric_theme.value.text()

    # Test clicking Monokai
    monokai_btn = panel.theme_buttons["monokai"]
    monokai_btn.click()
    assert theme_calls[-1] == "monokai"
    assert panel.current_theme == "monokai"
    assert monokai_btn.property("variant") == "primary"
    assert "Monokai" in panel.metric_theme.value.text()

    # Test clicking Catppuccin Mocha
    cat_btn = panel.theme_buttons["catppuccin"]
    cat_btn.click()
    assert theme_calls[-1] == "catppuccin"
    assert panel.current_theme == "catppuccin"
    assert cat_btn.property("variant") == "primary"
    assert "Catppuccin" in panel.metric_theme.value.text()


def test_qt_settings_panel_tabs_and_i18n_switching(qapp, tmp_path):
    translator = DesktopTranslator("vi")
    panel = QtSettingsPanel(
        QtCore,
        QtWidgets,
        translator,
        repo_root=tmp_path,
    )

    assert panel.tabs.count() == 4
    assert panel.tabs.tabText(0) == "Giao diện & Chủ đề"
    assert panel.tabs.tabText(1) == "Cấu hình nhanh .env"
    assert panel.tabs.tabText(2) == "Trình sửa tập tin .env"
    assert panel.tabs.tabText(3) == "Thông tin hệ thống"

    # Switch to English
    en_translator = DesktopTranslator("en")
    panel.set_translator(en_translator)

    assert panel.tabs.tabText(0) == "Theme & Appearance"
    assert panel.tabs.tabText(1) == "Quick .env Config"
    assert panel.tabs.tabText(2) == "Direct .env Editor"
    assert panel.tabs.tabText(3) == "System & Connection Info"
    assert panel.btn_save_form.text() == "💾  Save Settings to .env"
    assert panel.btn_save_raw.text() == "💾  Save .env"


def test_qt_settings_quick_config_form_saves_to_env(qapp, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("MCP_PORT=18427\nREQUIRE_AUTH=false\n", encoding="utf-8")

    saved_updates = []
    messages = []

    panel = QtSettingsPanel(
        QtCore,
        QtWidgets,
        DesktopTranslator("en"),
        repo_root=tmp_path,
        on_save_env=lambda upd: saved_updates.append(upd),
        on_message=lambda kind, msg: messages.append((kind, msg)),
    )

    # Modify form fields
    panel.input_mcp_port.setText("19450")
    panel.checkbox_require_auth.setChecked(True)
    panel.input_gateway_token.setText("custom_token_secret_999")
    panel.combo_command_policy.setCurrentText("allowlist")
    panel.spin_timeout.setValue(120)
    panel.spin_concurrency.setValue(50)

    # Click Save Form
    panel.btn_save_form.click()

    assert any(upd.get("MCP_PORT") == "19450" for upd in saved_updates)
    assert any(kind == "success" for kind, _ in messages)

    # Verify written to disk
    disk_content = env_file.read_text(encoding="utf-8")
    assert 'MCP_PORT="19450"' in disk_content
    assert 'REQUIRE_AUTH="true"' in disk_content
    assert 'GATEWAY_TOKEN="custom_token_secret_999"' in disk_content
    assert 'HOST_COMMAND_POLICY="allowlist"' in disk_content
    assert 'MAX_TIMEOUT_SECONDS="120"' in disk_content
    assert 'MAX_CONCURRENT_COMMANDS="50"' in disk_content

    # Verify raw editor was synced
    assert 'MCP_PORT="19450"' in panel.raw_env_editor.toPlainText()


def test_qt_settings_token_generation_and_visibility(qapp, tmp_path):
    panel = QtSettingsPanel(
        QtCore,
        QtWidgets,
        DesktopTranslator("en"),
        repo_root=tmp_path,
    )

    # Initially empty and password echo mode
    assert panel.input_gateway_token.echoMode() == QtWidgets.QLineEdit.Password
    assert panel.btn_toggle_token.text() == "👁"

    # Generate token
    panel.btn_gen_token.click()
    token = panel.input_gateway_token.text()
    assert len(token) == 64
    assert int(token, 16) > 0  # valid hex
    assert panel.checkbox_require_auth.isChecked() is True
    assert panel.input_gateway_token.echoMode() == QtWidgets.QLineEdit.Normal

    # Toggle visibility
    panel.btn_toggle_token.click()
    assert panel.input_gateway_token.echoMode() == QtWidgets.QLineEdit.Password
    panel.btn_toggle_token.click()
    assert panel.input_gateway_token.echoMode() == QtWidgets.QLineEdit.Normal


def test_qt_settings_raw_editor_and_validation(qapp, tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("REQUIRE_AUTH=true\nGATEWAY_TOKEN=\n", encoding="utf-8")

    messages = []
    panel = QtSettingsPanel(
        QtCore,
        QtWidgets,
        DesktopTranslator("en"),
        repo_root=tmp_path,
        on_message=lambda kind, msg: messages.append((kind, msg)),
    )

    # Validate initially invalid config (REQUIRE_AUTH=true but empty token)
    panel.btn_validate_env.click()
    assert any(kind == "error" for kind, _ in messages)
    assert "❌" in panel.lbl_validate_status.text()

    # Edit raw text directly in editor
    valid_text = (
        'MCP_PORT="18427"\n'
        'REQUIRE_AUTH="false"\n'
        'GATEWAY_TOKEN=""\n'
        'HOST_WORKSPACE_DIR="{}"\n'
    ).format(str(tmp_path))
    panel.raw_env_editor.setPlainText(valid_text)

    # Save raw editor
    panel.btn_save_raw.click()
    assert any(kind == "success" and "mode 0600" in msg.lower() for kind, msg in messages)

    # Verify disk content and mode
    assert env_file.read_text(encoding="utf-8") == valid_text
    mode = env_file.stat().st_mode & 0o777
    assert mode == 0o600

    # Validate again with mock returning passing checks
    messages.clear()
    monkeypatch.setattr(
        "app.cli.desktop_qt.settings.validate_config",
        lambda repo, env: [{"name": "test_item", "status": "pass"}],
    )
    panel.btn_validate_env.click()
    assert any(kind == "success" for kind, _ in messages)
    assert "✅" in panel.lbl_validate_status.text()


def test_set_desktop_ui_theme_persists_to_env(tmp_path, monkeypatch):
    from app.cli.config_view import set_desktop_ui_theme, load_env

    monkeypatch.delenv("BQA_UI_THEME", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("MCP_PORT=18427\n", encoding="utf-8")

    updated = set_desktop_ui_theme(tmp_path, "tokyo_night")
    assert updated["BQA_UI_THEME"] == "tokyo_night"

    values = load_env(tmp_path)
    assert values["BQA_UI_THEME"] == "tokyo_night"

