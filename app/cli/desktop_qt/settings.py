"""PySide Settings panel for managing language, themes, and .env configuration."""

from __future__ import annotations

import os
from pathlib import Path
import platform
import sys
from typing import Any, Callable

from app.cli.config_view import (
    generate_secure_token,
    load_env,
    load_raw_env,
    save_raw_env,
    save_env_key_values,
    validate_config,
)
from app.cli.desktop_qt.theme import LAYOUT, list_available_themes
from app.cli.desktop_qt.widgets import MetricCell, SectionHeading, apply_button_variant
from app.cli.desktop_views.i18n import DesktopTranslator


class QtSettingsPanel:
    """Render Settings tab with Theme selection (10+ themes), Language, and .env Editing."""

    def __init__(
        self,
        QtCore: Any,
        QtWidgets: Any,
        translator: DesktopTranslator,
        *,
        current_theme: str = "dark",
        on_change_language: Callable[[str], None] | None = None,
        on_change_theme: Callable[[str], None] | None = None,
        get_workspace: Callable[[], str] | None = None,
        on_message: Callable[[str, str], None] | None = None,
        repo_root: Path | None = None,
        on_save_env: Callable[[dict[str, str]], None] | None = None,
    ) -> None:
        self.QtCore = QtCore
        self.QtWidgets = QtWidgets
        self.translator = translator
        self.current_theme = current_theme
        self.on_change_language = on_change_language or (lambda lang: None)
        self.on_change_theme = on_change_theme or (lambda theme: None)
        self.get_workspace = get_workspace or (lambda: "")
        self.on_message = on_message or (lambda kind, msg: None)
        self.repo_root = Path(repo_root) if repo_root else Path.cwd()
        self.on_save_env = on_save_env or (lambda updates: None)

        self.widget = QtWidgets.QWidget()
        self.widget.setObjectName("settingsPage")
        layout = QtWidgets.QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(LAYOUT["space_md"])

        # 1. Header Frame with Title
        self.header_frame = QtWidgets.QFrame()
        self.header_frame.setObjectName("settingsHeaderFrame")
        header_layout = QtWidgets.QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(LAYOUT["space_sm"])

        self.heading = SectionHeading(
            QtWidgets,
            translator.text("settings.title"),
            translator.text("settings.subtitle"),
        )
        self.heading.widget.setObjectName("settingsHeader")
        header_layout.addWidget(self.heading.widget)
        header_layout.addStretch(1)
        layout.addWidget(self.header_frame)

        # 2. Metric Strip
        self.metric_strip = QtWidgets.QFrame()
        self.metric_strip.setObjectName("metricStrip")
        self.metric_strip.setProperty("role", "card")
        self.metric_strip.setMinimumHeight(76)
        metric_layout = QtWidgets.QHBoxLayout(self.metric_strip)
        metric_layout.setContentsMargins(12, 8, 12, 8)
        metric_layout.setSpacing(8)

        theme_key = f"settings.theme_{self.current_theme}"
        theme_text = translator.text(theme_key)
        if theme_text == theme_key:
            theme_text = self.current_theme.replace("_", " ").title()

        lang_text = (
            translator.text("language.vi")
            if self.translator.language == "vi"
            else translator.text("language.en")
        )

        env_file = self.repo_root / ".env"
        env_status_text = "Mode 0600" if env_file.exists() else "Default (.env.example)"

        self.metric_theme = MetricCell(
            QtWidgets,
            translator.text("settings.active_theme"),
            theme_text,
        )
        self.metric_lang = MetricCell(
            QtWidgets,
            translator.text("settings.active_language"),
            lang_text,
        )
        self.metric_ver = MetricCell(
            QtWidgets,
            translator.text("settings.app_version"),
            "UCS 1.0.0",
        )
        self.metric_env = MetricCell(
            QtWidgets,
            translator.text("settings.metric_config"),
            env_status_text,
        )

        for cell in (self.metric_theme, self.metric_lang, self.metric_ver, self.metric_env):
            cell.widget.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding,
                QtWidgets.QSizePolicy.Preferred,
            )
            metric_layout.addWidget(cell.widget, 1)

        layout.addWidget(self.metric_strip)

        # 3. Sub Tabs for Settings
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setObjectName("settingsTabs")

        # Build each tab view
        self._build_appearance_tab()
        self._build_quick_config_tab()
        self._build_raw_editor_tab()
        self._build_system_info_tab()

        self.tabs.addTab(self.appearance_tab, translator.text("settings.tab.appearance"))
        self.tabs.addTab(self.quick_config_tab, translator.text("settings.tab.quick_config"))
        self.tabs.addTab(self.raw_editor_tab, translator.text("settings.tab.raw_editor"))
        self.tabs.addTab(self.system_info_tab, translator.text("settings.tab.system_info"))

        layout.addWidget(self.tabs, 1)

        self._update_button_states()

    def _build_appearance_tab(self) -> None:
        """Tab 0: Theme Selection (12 themes) & Language Selection."""
        self.appearance_tab = self.QtWidgets.QWidget()
        tab_layout = self.QtWidgets.QHBoxLayout(self.appearance_tab)
        tab_layout.setContentsMargins(0, 8, 0, 0)
        tab_layout.setSpacing(LAYOUT["space_md"])

        # Card A: Theme / Appearance
        self.theme_card = self.QtWidgets.QFrame()
        self.theme_card.setObjectName("themeCard")
        self.theme_card.setProperty("role", "card")
        theme_card_layout = self.QtWidgets.QVBoxLayout(self.theme_card)
        theme_card_layout.setContentsMargins(16, 14, 16, 16)
        theme_card_layout.setSpacing(10)

        self.theme_heading = self.QtWidgets.QLabel(self.translator.text("settings.appearance"))
        self.theme_heading.setProperty("role", "cardTitle")
        theme_card_layout.addWidget(self.theme_heading)

        self.theme_desc = self.QtWidgets.QLabel(self.translator.text("settings.theme_desc"))
        self.theme_desc.setProperty("role", "footerStatus")
        self.theme_desc.setWordWrap(True)
        theme_card_layout.addWidget(self.theme_desc)

        # Scrollable list for themes
        self.theme_scroll = self.QtWidgets.QScrollArea()
        self.theme_scroll.setWidgetResizable(True)
        self.theme_scroll.setFrameShape(self.QtWidgets.QFrame.NoFrame)
        self.theme_scroll.setStyleSheet("QScrollArea { background: transparent; border: 0; }")

        theme_scroll_content = self.QtWidgets.QWidget()
        theme_scroll_content.setStyleSheet("background: transparent;")
        theme_items_layout = self.QtWidgets.QVBoxLayout(theme_scroll_content)
        theme_items_layout.setContentsMargins(0, 0, 4, 0)
        theme_items_layout.setSpacing(8)

        self.theme_buttons: dict[str, Any] = {}
        self.theme_descs: dict[str, Any] = {}

        for theme_info in list_available_themes():
            t_id = theme_info["id"]
            t_key = f"settings.theme_{t_id}"
            t_name = self.translator.text(t_key)
            if t_name == t_key:
                t_name = t_id.replace("_", " ").title()

            btn = self.QtWidgets.QPushButton(f"{theme_info['icon']}  {t_name}")
            btn.setProperty("role", "compactAction")
            btn.clicked.connect(lambda _, tid=t_id: self._apply_theme(tid))
            theme_items_layout.addWidget(btn)
            self.theme_buttons[t_id] = btn

            d_key = f"settings.theme_{t_id}_desc"
            d_text = self.translator.text(d_key)
            if d_text == d_key:
                d_text = ""
            desc = self.QtWidgets.QLabel(d_text)
            desc.setProperty("role", "footerStatus")
            desc.setWordWrap(True)
            theme_items_layout.addWidget(desc)
            self.theme_descs[t_id] = desc

            theme_items_layout.addSpacing(2)

        theme_items_layout.addStretch(1)
        self.theme_scroll.setWidget(theme_scroll_content)
        theme_card_layout.addWidget(self.theme_scroll, 1)

        # Backward compatibility bindings for existing tests
        self.dark_button = self.theme_buttons.get("dark")
        self.light_button = self.theme_buttons.get("light")
        self.dark_desc = self.theme_descs.get("dark")
        self.light_desc = self.theme_descs.get("light")

        tab_layout.addWidget(self.theme_card, 3)

        # Card B: Language
        self.lang_card = self.QtWidgets.QFrame()
        self.lang_card.setObjectName("langCard")
        self.lang_card.setProperty("role", "card")
        lang_card_layout = self.QtWidgets.QVBoxLayout(self.lang_card)
        lang_card_layout.setContentsMargins(16, 14, 16, 16)
        lang_card_layout.setSpacing(10)

        self.lang_heading = self.QtWidgets.QLabel(self.translator.text("settings.language"))
        self.lang_heading.setProperty("role", "cardTitle")
        lang_card_layout.addWidget(self.lang_heading)

        self.lang_desc = self.QtWidgets.QLabel(self.translator.text("settings.language_desc"))
        self.lang_desc.setProperty("role", "footerStatus")
        self.lang_desc.setWordWrap(True)
        lang_card_layout.addWidget(self.lang_desc)

        # Lang Option 1: Tiếng Việt
        self.vi_button = self.QtWidgets.QPushButton("🇻🇳  Tiếng Việt")
        self.vi_button.setProperty("role", "compactAction")
        self.vi_button.clicked.connect(lambda: self._apply_language("vi"))
        lang_card_layout.addWidget(self.vi_button)

        self.vi_desc = self.QtWidgets.QLabel(
            "Giao diện người dùng và tài liệu hỗ trợ hoàn toàn bằng Tiếng Việt."
        )
        self.vi_desc.setProperty("role", "footerStatus")
        self.vi_desc.setWordWrap(True)
        lang_card_layout.addWidget(self.vi_desc)

        lang_card_layout.addSpacing(6)

        # Lang Option 2: English
        self.en_button = self.QtWidgets.QPushButton("🇬🇧  English")
        self.en_button.setProperty("role", "compactAction")
        self.en_button.clicked.connect(lambda: self._apply_language("en"))
        lang_card_layout.addWidget(self.en_button)

        self.en_desc = self.QtWidgets.QLabel(
            "International English interface, labels, and standard prompt templates."
        )
        self.en_desc.setProperty("role", "footerStatus")
        self.en_desc.setWordWrap(True)
        lang_card_layout.addWidget(self.en_desc)

        lang_card_layout.addStretch(1)
        tab_layout.addWidget(self.lang_card, 2)

    def _build_quick_config_tab(self) -> None:
        """Tab 1: Quick form-based .env configuration."""
        self.quick_config_tab = self.QtWidgets.QWidget()
        tab_layout = self.QtWidgets.QVBoxLayout(self.quick_config_tab)
        tab_layout.setContentsMargins(0, 8, 0, 0)
        tab_layout.setSpacing(LAYOUT["space_md"])

        scroll = self.QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(self.QtWidgets.QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: 0; }")

        scroll_content = self.QtWidgets.QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        form_layout = self.QtWidgets.QVBoxLayout(scroll_content)
        form_layout.setContentsMargins(0, 0, 8, 0)
        form_layout.setSpacing(12)

        env_values = load_env(self.repo_root)

        # Section 1: Network & Auth
        self.sec_net_card = self.QtWidgets.QFrame()
        self.sec_net_card.setProperty("role", "card")
        sec_net_layout = self.QtWidgets.QVBoxLayout(self.sec_net_card)
        sec_net_layout.setContentsMargins(16, 12, 16, 14)
        sec_net_layout.setSpacing(8)

        self.lbl_sec_net = self.QtWidgets.QLabel(self.translator.text("settings.form.section_network"))
        self.lbl_sec_net.setProperty("role", "cardTitle")
        sec_net_layout.addWidget(self.lbl_sec_net)

        net_grid = self.QtWidgets.QGridLayout()
        net_grid.setHorizontalSpacing(12)
        net_grid.setVerticalSpacing(8)

        # Port
        self.lbl_form_port = self.QtWidgets.QLabel(self.translator.text("settings.form.mcp_port"))
        self.lbl_form_port.setProperty("role", "fieldKey")
        self.input_mcp_port = self.QtWidgets.QLineEdit(env_values.get("MCP_PORT", "18427"))
        net_grid.addWidget(self.lbl_form_port, 0, 0)
        net_grid.addWidget(self.input_mcp_port, 0, 1)

        # Bind Host
        self.lbl_form_host = self.QtWidgets.QLabel(self.translator.text("settings.form.bind_host"))
        self.lbl_form_host.setProperty("role", "fieldKey")
        self.input_bind_host = self.QtWidgets.QLineEdit(env_values.get("MCP_BIND_HOST", "127.0.0.1"))
        net_grid.addWidget(self.lbl_form_host, 0, 2)
        net_grid.addWidget(self.input_bind_host, 0, 3)

        # Require Auth checkbox
        self.checkbox_require_auth = self.QtWidgets.QCheckBox(self.translator.text("settings.form.require_auth"))
        req_auth = env_values.get("REQUIRE_AUTH", "false").strip().lower() in {"1", "true", "yes"}
        self.checkbox_require_auth.setChecked(req_auth)
        net_grid.addWidget(self.checkbox_require_auth, 1, 0, 1, 4)

        # Gateway Token
        self.lbl_form_token = self.QtWidgets.QLabel(self.translator.text("settings.form.gateway_token"))
        self.lbl_form_token.setProperty("role", "fieldKey")
        net_grid.addWidget(self.lbl_form_token, 2, 0)

        token_box = self.QtWidgets.QHBoxLayout()
        token_box.setSpacing(6)
        self.input_gateway_token = self.QtWidgets.QLineEdit(env_values.get("GATEWAY_TOKEN", ""))
        self.input_gateway_token.setEchoMode(self.QtWidgets.QLineEdit.Password)
        token_box.addWidget(self.input_gateway_token, 1)

        self.btn_toggle_token = self.QtWidgets.QPushButton("👁")
        self.btn_toggle_token.setFixedWidth(34)
        self.btn_toggle_token.setProperty("role", "compactAction")
        self.btn_toggle_token.clicked.connect(self._toggle_token_visibility)
        token_box.addWidget(self.btn_toggle_token)

        self.btn_gen_token = self.QtWidgets.QPushButton(f"🔑 {self.translator.text('settings.form.generate_token')}")
        self.btn_gen_token.setProperty("role", "compactAction")
        self.btn_gen_token.clicked.connect(self._generate_new_token)
        token_box.addWidget(self.btn_gen_token)

        net_grid.addLayout(token_box, 2, 1, 1, 3)
        sec_net_layout.addLayout(net_grid)
        form_layout.addWidget(self.sec_net_card)

        # Section 2: Host & Workspace
        self.sec_host_card = self.QtWidgets.QFrame()
        self.sec_host_card.setProperty("role", "card")
        sec_host_layout = self.QtWidgets.QVBoxLayout(self.sec_host_card)
        sec_host_layout.setContentsMargins(16, 12, 16, 14)
        sec_host_layout.setSpacing(8)

        self.lbl_sec_host = self.QtWidgets.QLabel(self.translator.text("settings.form.section_host"))
        self.lbl_sec_host.setProperty("role", "cardTitle")
        sec_host_layout.addWidget(self.lbl_sec_host)

        host_grid = self.QtWidgets.QGridLayout()
        host_grid.setHorizontalSpacing(12)
        host_grid.setVerticalSpacing(8)

        # Workspace Dir
        self.lbl_form_ws = self.QtWidgets.QLabel(self.translator.text("settings.form.workspace_dir"))
        self.lbl_form_ws.setProperty("role", "fieldKey")
        host_grid.addWidget(self.lbl_form_ws, 0, 0)

        ws_box = self.QtWidgets.QHBoxLayout()
        ws_box.setSpacing(6)
        ws_val = env_values.get("HOST_WORKSPACE_DIR") or self.get_workspace() or str(Path.home())
        self.input_workspace_dir = self.QtWidgets.QLineEdit(ws_val)
        ws_box.addWidget(self.input_workspace_dir, 1)

        self.btn_browse_ws = self.QtWidgets.QPushButton(f"📂 {self.translator.text('settings.form.choose_folder')}")
        self.btn_browse_ws.setProperty("role", "compactAction")
        self.btn_browse_ws.clicked.connect(self._browse_workspace)
        ws_box.addWidget(self.btn_browse_ws)
        host_grid.addLayout(ws_box, 0, 1, 1, 3)

        # Policy & Chat Isolation
        self.lbl_form_policy = self.QtWidgets.QLabel(self.translator.text("settings.form.command_policy"))
        self.lbl_form_policy.setProperty("role", "fieldKey")
        self.combo_command_policy = self.QtWidgets.QComboBox()
        self.combo_command_policy.addItems(["guarded", "allowlist"])
        current_pol = env_values.get("HOST_COMMAND_POLICY", "guarded").strip().lower()
        if current_pol in ["guarded", "allowlist"]:
            self.combo_command_policy.setCurrentText(current_pol)
        host_grid.addWidget(self.lbl_form_policy, 1, 0)
        host_grid.addWidget(self.combo_command_policy, 1, 1)

        self.checkbox_chat_workspaces = self.QtWidgets.QCheckBox(self.translator.text("settings.form.chat_workspaces"))
        chat_ws = env_values.get("HOST_CHAT_WORKSPACES", "true").strip().lower() in {"1", "true", "yes"}
        self.checkbox_chat_workspaces.setChecked(chat_ws)
        host_grid.addWidget(self.checkbox_chat_workspaces, 1, 2, 1, 2)

        sec_host_layout.addLayout(host_grid)
        form_layout.addWidget(self.sec_host_card)

        # Section 3: Performance & Limits
        self.sec_limits_card = self.QtWidgets.QFrame()
        self.sec_limits_card.setProperty("role", "card")
        sec_limits_layout = self.QtWidgets.QVBoxLayout(self.sec_limits_card)
        sec_limits_layout.setContentsMargins(16, 12, 16, 14)
        sec_limits_layout.setSpacing(8)

        self.lbl_sec_limits = self.QtWidgets.QLabel(self.translator.text("settings.form.section_limits"))
        self.lbl_sec_limits.setProperty("role", "cardTitle")
        sec_limits_layout.addWidget(self.lbl_sec_limits)

        limits_grid = self.QtWidgets.QGridLayout()
        limits_grid.setHorizontalSpacing(12)
        limits_grid.setVerticalSpacing(8)

        # Timeout
        self.lbl_form_timeout = self.QtWidgets.QLabel(self.translator.text("settings.form.timeout_seconds"))
        self.lbl_form_timeout.setProperty("role", "fieldKey")
        self.spin_timeout = self.QtWidgets.QSpinBox()
        self.spin_timeout.setRange(1, 3600)
        self.spin_timeout.setValue(int(env_values.get("MAX_TIMEOUT_SECONDS", "60")))
        limits_grid.addWidget(self.lbl_form_timeout, 0, 0)
        limits_grid.addWidget(self.spin_timeout, 0, 1)

        # Max Concurrency
        self.lbl_form_concurrency = self.QtWidgets.QLabel(self.translator.text("settings.form.max_concurrency"))
        self.lbl_form_concurrency.setProperty("role", "fieldKey")
        self.spin_concurrency = self.QtWidgets.QSpinBox()
        self.spin_concurrency.setRange(1, 1024)
        self.spin_concurrency.setValue(int(env_values.get("MAX_CONCURRENT_COMMANDS", "100")))
        limits_grid.addWidget(self.lbl_form_concurrency, 0, 2)
        limits_grid.addWidget(self.spin_concurrency, 0, 3)

        # Max output bytes
        self.lbl_form_max_output = self.QtWidgets.QLabel(self.translator.text("settings.form.max_output_bytes"))
        self.lbl_form_max_output.setProperty("role", "fieldKey")
        self.input_max_output = self.QtWidgets.QLineEdit(env_values.get("MAX_OUTPUT_BYTES", "0"))
        limits_grid.addWidget(self.lbl_form_max_output, 1, 0)
        limits_grid.addWidget(self.input_max_output, 1, 1, 1, 3)

        sec_limits_layout.addLayout(limits_grid)
        form_layout.addWidget(self.sec_limits_card)

        form_layout.addStretch(1)
        scroll.setWidget(scroll_content)
        tab_layout.addWidget(scroll, 1)

        # Bottom Form Actions Bar
        actions_bar = self.QtWidgets.QHBoxLayout()
        actions_bar.setContentsMargins(0, 4, 0, 0)
        actions_bar.setSpacing(8)

        self.btn_save_form = self.QtWidgets.QPushButton(f"💾  {self.translator.text('settings.form.save')}")
        self.btn_save_form.setProperty("role", "primaryAction")
        apply_button_variant(self.btn_save_form, "primary")
        self.btn_save_form.clicked.connect(self._save_form_changes)
        actions_bar.addWidget(self.btn_save_form)

        self.btn_reset_form = self.QtWidgets.QPushButton(f"🔄  {self.translator.text('settings.form.reset')}")
        self.btn_reset_form.setProperty("role", "compactAction")
        self.btn_reset_form.clicked.connect(self._reload_form_values)
        actions_bar.addWidget(self.btn_reset_form)

        actions_bar.addStretch(1)
        tab_layout.addLayout(actions_bar)

    def _build_raw_editor_tab(self) -> None:
        """Tab 2: Direct text editor for raw .env file with validation."""
        self.raw_editor_tab = self.QtWidgets.QWidget()
        tab_layout = self.QtWidgets.QVBoxLayout(self.raw_editor_tab)
        tab_layout.setContentsMargins(0, 8, 0, 0)
        tab_layout.setSpacing(8)

        # Path info card
        header_card = self.QtWidgets.QFrame()
        header_card.setProperty("role", "card")
        header_layout = self.QtWidgets.QHBoxLayout(header_card)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(12)

        env_path = self.repo_root / ".env"
        self.lbl_raw_path = self.QtWidgets.QLabel(
            self.translator.text("settings.raw.target_file", path=str(env_path))
        )
        self.lbl_raw_path.setProperty("role", "fieldKey")
        header_layout.addWidget(self.lbl_raw_path, 1)

        self.lbl_raw_notice = self.QtWidgets.QLabel(self.translator.text("settings.raw.notice"))
        self.lbl_raw_notice.setProperty("role", "footerStatus")
        header_layout.addWidget(self.lbl_raw_notice)
        tab_layout.addWidget(header_card)

        # Monospace Text Editor
        self.raw_env_editor = self.QtWidgets.QPlainTextEdit()
        self.raw_env_editor.setObjectName("rawEnvEditor")
        self.raw_env_editor.setLineWrapMode(self.QtWidgets.QPlainTextEdit.NoWrap)
        font = self.raw_env_editor.font()
        font.setFamily("monospace")
        self.raw_env_editor.setFont(font)
        self.raw_env_editor.setPlainText(load_raw_env(self.repo_root))
        tab_layout.addWidget(self.raw_env_editor, 1)

        # Action Buttons
        actions_layout = self.QtWidgets.QHBoxLayout()
        actions_layout.setContentsMargins(0, 2, 0, 0)
        actions_layout.setSpacing(8)

        self.btn_save_raw = self.QtWidgets.QPushButton(f"💾  {self.translator.text('settings.raw.save')}")
        self.btn_save_raw.setProperty("role", "primaryAction")
        apply_button_variant(self.btn_save_raw, "primary")
        self.btn_save_raw.clicked.connect(self._save_raw_changes)
        actions_layout.addWidget(self.btn_save_raw)

        self.btn_reload_raw = self.QtWidgets.QPushButton(f"🔄  {self.translator.text('settings.raw.reload')}")
        self.btn_reload_raw.setProperty("role", "compactAction")
        self.btn_reload_raw.clicked.connect(self._reload_raw_content)
        actions_layout.addWidget(self.btn_reload_raw)

        self.btn_validate_env = self.QtWidgets.QPushButton(f"✨  {self.translator.text('settings.raw.validate')}")
        self.btn_validate_env.setProperty("role", "compactAction")
        self.btn_validate_env.clicked.connect(self._validate_env_config)
        actions_layout.addWidget(self.btn_validate_env)

        self.btn_load_example = self.QtWidgets.QPushButton(f"📋  {self.translator.text('settings.raw.load_example')}")
        self.btn_load_example.setProperty("role", "compactAction")
        self.btn_load_example.clicked.connect(self._load_example_template)
        actions_layout.addWidget(self.btn_load_example)

        self.lbl_validate_status = self.QtWidgets.QLabel("")
        self.lbl_validate_status.setProperty("role", "footerStatus")
        actions_layout.addWidget(self.lbl_validate_status, 1)

        tab_layout.addLayout(actions_layout)

    def _build_system_info_tab(self) -> None:
        """Tab 3: System Information & Diagnostics (maintains backward compatibility)."""
        self.system_info_tab = self.QtWidgets.QWidget()
        tab_layout = self.QtWidgets.QVBoxLayout(self.system_info_tab)
        tab_layout.setContentsMargins(0, 8, 0, 0)
        tab_layout.setSpacing(LAYOUT["space_md"])

        self.info_card = self.QtWidgets.QFrame()
        self.info_card.setObjectName("infoCard")
        self.info_card.setProperty("role", "card")
        info_card_layout = self.QtWidgets.QVBoxLayout(self.info_card)
        info_card_layout.setContentsMargins(16, 14, 16, 16)
        info_card_layout.setSpacing(10)

        self.info_heading = self.QtWidgets.QLabel(self.translator.text("settings.system_info"))
        self.info_heading.setProperty("role", "cardTitle")
        info_card_layout.addWidget(self.info_heading)

        self.info_desc = self.QtWidgets.QLabel(self.translator.text("settings.system_desc"))
        self.info_desc.setProperty("role", "footerStatus")
        self.info_desc.setWordWrap(True)
        info_card_layout.addWidget(self.info_desc)

        # Standard rows retained for compatibility
        self.ws_row = self.QtWidgets.QLabel(f"Workspace: {self.get_workspace() or '~'}")
        self.ws_row.setProperty("role", "footerStatus")
        self.ws_row.setWordWrap(True)
        info_card_layout.addWidget(self.ws_row)

        self.proto_row = self.QtWidgets.QLabel("Protocol: Streamable HTTP (FastMCP 3.4.7)")
        self.proto_row.setProperty("role", "footerStatus")
        info_card_layout.addWidget(self.proto_row)

        self.port_row = self.QtWidgets.QLabel("Port: 18427 (MCP Loopback Bridge)")
        self.port_row.setProperty("role", "footerStatus")
        info_card_layout.addWidget(self.port_row)

        # Diagnostics & Runtime details
        env_path = self.repo_root / ".env"
        env_state = "Found (mode 0600)" if env_path.is_file() else "Missing (fallback to defaults)"
        self.env_path_row = self.QtWidgets.QLabel(f".env File: {env_path} [{env_state}]")
        self.env_path_row.setProperty("role", "footerStatus")
        self.env_path_row.setWordWrap(True)
        info_card_layout.addWidget(self.env_path_row)

        self.platform_row = self.QtWidgets.QLabel(f"Platform: {platform.platform()} (Python {sys.version.split()[0]})")
        self.platform_row.setProperty("role", "footerStatus")
        info_card_layout.addWidget(self.platform_row)

        info_card_layout.addStretch(1)
        tab_layout.addWidget(self.info_card, 1)

    # --- Actions & Handlers ---

    def _toggle_token_visibility(self) -> None:
        if self.input_gateway_token.echoMode() == self.QtWidgets.QLineEdit.Password:
            self.input_gateway_token.setEchoMode(self.QtWidgets.QLineEdit.Normal)
            self.btn_toggle_token.setText("🔒")
        else:
            self.input_gateway_token.setEchoMode(self.QtWidgets.QLineEdit.Password)
            self.btn_toggle_token.setText("👁")

    def _generate_new_token(self) -> None:
        new_token = generate_secure_token()
        self.input_gateway_token.setText(new_token)
        self.input_gateway_token.setEchoMode(self.QtWidgets.QLineEdit.Normal)
        self.btn_toggle_token.setText("🔒")
        self.checkbox_require_auth.setChecked(True)
        self.on_message("info", "Generated new cryptographic 64-hex token.")

    def _browse_workspace(self) -> None:
        current = self.input_workspace_dir.text() or str(Path.home())
        selected = self.QtWidgets.QFileDialog.getExistingDirectory(
            self.widget,
            self.translator.text("action.choose_folder"),
            current,
        )
        if selected:
            self.input_workspace_dir.setText(selected)

    def _save_form_changes(self) -> None:
        """Persist quick form changes into .env file."""
        updates: dict[str, str] = {
            "MCP_PORT": self.input_mcp_port.text().strip(),
            "MCP_BIND_HOST": self.input_bind_host.text().strip(),
            "REQUIRE_AUTH": "true" if self.checkbox_require_auth.isChecked() else "false",
            "GATEWAY_TOKEN": self.input_gateway_token.text().strip(),
            "HOST_WORKSPACE_DIR": self.input_workspace_dir.text().strip(),
            "HOST_DEFAULT_DIR": self.input_workspace_dir.text().strip(),
            "HOST_COMMAND_POLICY": self.combo_command_policy.currentText(),
            "HOST_CHAT_WORKSPACES": "true" if self.checkbox_chat_workspaces.isChecked() else "false",
            "MAX_TIMEOUT_SECONDS": str(self.spin_timeout.value()),
            "MAX_CONCURRENT_COMMANDS": str(self.spin_concurrency.value()),
            "MAX_OUTPUT_BYTES": self.input_max_output.text().strip(),
        }
        try:
            saved = save_env_key_values(self.repo_root, updates)
            # Sync raw editor text
            self.raw_env_editor.setPlainText(load_raw_env(self.repo_root))
            self.on_save_env(saved)
            self.on_message("success", self.translator.text("settings.env_saved"))
            self.metric_env.value.setText("Mode 0600")
        except Exception as exc:
            self.on_message("error", self.translator.text("settings.env_error", error=str(exc)))

    def _reload_form_values(self) -> None:
        """Reset form to reflect disk state."""
        env_values = load_env(self.repo_root)
        self.input_mcp_port.setText(env_values.get("MCP_PORT", "18427"))
        self.input_bind_host.setText(env_values.get("MCP_BIND_HOST", "127.0.0.1"))
        req_auth = env_values.get("REQUIRE_AUTH", "false").strip().lower() in {"1", "true", "yes"}
        self.checkbox_require_auth.setChecked(req_auth)
        self.input_gateway_token.setText(env_values.get("GATEWAY_TOKEN", ""))
        ws_val = env_values.get("HOST_WORKSPACE_DIR") or self.get_workspace() or str(Path.home())
        self.input_workspace_dir.setText(ws_val)
        current_pol = env_values.get("HOST_COMMAND_POLICY", "guarded").strip().lower()
        if current_pol in ["guarded", "allowlist"]:
            self.combo_command_policy.setCurrentText(current_pol)
        chat_ws = env_values.get("HOST_CHAT_WORKSPACES", "true").strip().lower() in {"1", "true", "yes"}
        self.checkbox_chat_workspaces.setChecked(chat_ws)
        self.spin_timeout.setValue(int(env_values.get("MAX_TIMEOUT_SECONDS", "60")))
        self.spin_concurrency.setValue(int(env_values.get("MAX_CONCURRENT_COMMANDS", "100")))
        self.input_max_output.setText(env_values.get("MAX_OUTPUT_BYTES", "0"))
        self.on_message("info", self.translator.text("settings.env_reloaded"))

    def _save_raw_changes(self) -> None:
        """Persist raw editor contents into .env with mode 0600."""
        content = self.raw_env_editor.toPlainText()
        try:
            save_raw_env(self.repo_root, content)
            updated_env = load_env(self.repo_root)
            self._reload_form_values()
            self.on_save_env(updated_env)
            self.on_message("success", self.translator.text("settings.env_raw_saved"))
            self.metric_env.value.setText("Mode 0600")
        except Exception as exc:
            self.on_message("error", self.translator.text("settings.env_error", error=str(exc)))

    def _reload_raw_content(self) -> None:
        self.raw_env_editor.setPlainText(load_raw_env(self.repo_root))
        self.on_message("info", self.translator.text("settings.env_reloaded"))

    def _load_example_template(self) -> None:
        example_path = self.repo_root / ".env.example"
        if example_path.is_file():
            try:
                self.raw_env_editor.setPlainText(example_path.read_text(encoding="utf-8"))
                self.on_message("info", self.translator.text("settings.env_example_loaded"))
            except Exception as exc:
                self.on_message("error", str(exc))

    def _validate_env_config(self) -> None:
        env_values = load_env(self.repo_root)
        checks = validate_config(self.repo_root, env_values)
        passed = sum(1 for c in checks if c["status"] == "pass")
        warnings = sum(1 for c in checks if c["status"] == "warn")
        failures = sum(1 for c in checks if c["status"] == "fail")

        if failures > 0:
            msg = self.translator.text("settings.validate_fail", failures=failures)
            self.lbl_validate_status.setText(f"❌ {msg}")
            self.on_message("error", msg)
        elif warnings > 0:
            msg = self.translator.text("settings.validate_warn", warnings=warnings, passed=passed)
            self.lbl_validate_status.setText(f"⚠️ {msg}")
            self.on_message("warn", msg)
        else:
            msg = self.translator.text("settings.validate_success", passed=passed)
            self.lbl_validate_status.setText(f"✅ {msg}")
            self.on_message("success", msg)

    def _apply_theme(self, theme: str) -> None:
        self.current_theme = theme
        theme_key = f"settings.theme_{theme}"
        theme_text = self.translator.text(theme_key)
        if theme_text == theme_key:
            theme_text = theme.replace("_", " ").title()
        self.metric_theme.value.setText(theme_text)
        self._update_button_states()
        self.on_change_theme(theme)

    def _apply_language(self, lang: str) -> None:
        self._update_button_states()
        self.on_change_language(lang)

    def set_theme(self, theme: str) -> None:
        self.current_theme = theme
        self._update_button_states()
        theme_key = f"settings.theme_{theme}"
        theme_text = self.translator.text(theme_key)
        if theme_text == theme_key:
            theme_text = theme.replace("_", " ").title()
        self.metric_theme.value.setText(theme_text)

    def _update_button_states(self) -> None:
        # Theme buttons
        for tid, btn in self.theme_buttons.items():
            if tid == self.current_theme:
                apply_button_variant(btn, "primary")
            else:
                apply_button_variant(btn, "secondary")

        # Language buttons
        if self.translator.language == "vi":
            apply_button_variant(self.vi_button, "primary")
            apply_button_variant(self.en_button, "secondary")
        else:
            apply_button_variant(self.vi_button, "secondary")
            apply_button_variant(self.en_button, "primary")

    def set_translator(self, translator: DesktopTranslator) -> None:
        self.translator = translator
        self.heading.title_label.setText(translator.text("settings.title"))
        self.heading.eyebrow_label.setText(translator.text("settings.subtitle"))

        # Tabs labels
        self.tabs.setTabText(0, translator.text("settings.tab.appearance"))
        self.tabs.setTabText(1, translator.text("settings.tab.quick_config"))
        self.tabs.setTabText(2, translator.text("settings.tab.raw_editor"))
        self.tabs.setTabText(3, translator.text("settings.tab.system_info"))

        # Appearance
        self.theme_heading.setText(translator.text("settings.appearance"))
        self.theme_desc.setText(translator.text("settings.theme_desc"))

        for theme_info in list_available_themes():
            tid = theme_info["id"]
            btn = self.theme_buttons.get(tid)
            lbl = self.theme_descs.get(tid)
            if btn is not None:
                t_key = f"settings.theme_{tid}"
                t_name = translator.text(t_key)
                if t_name == t_key:
                    t_name = tid.replace("_", " ").title()
                btn.setText(f"{theme_info['icon']}  {t_name}")
            if lbl is not None:
                d_key = f"settings.theme_{tid}_desc"
                d_text = translator.text(d_key)
                if d_text == d_key:
                    d_text = ""
                lbl.setText(d_text)

        self.lang_heading.setText(translator.text("settings.language"))
        self.lang_desc.setText(translator.text("settings.language_desc"))

        # Quick config form labels
        self.lbl_sec_net.setText(translator.text("settings.form.section_network"))
        self.lbl_form_port.setText(translator.text("settings.form.mcp_port"))
        self.lbl_form_host.setText(translator.text("settings.form.bind_host"))
        self.checkbox_require_auth.setText(translator.text("settings.form.require_auth"))
        self.lbl_form_token.setText(translator.text("settings.form.gateway_token"))
        self.btn_gen_token.setText(f"🔑  {translator.text('settings.form.generate_token')}")

        self.lbl_sec_host.setText(translator.text("settings.form.section_host"))
        self.lbl_form_ws.setText(translator.text("settings.form.workspace_dir"))
        self.btn_browse_ws.setText(f"📂  {translator.text('settings.form.choose_folder')}")
        self.lbl_form_policy.setText(translator.text("settings.form.command_policy"))
        self.checkbox_chat_workspaces.setText(translator.text("settings.form.chat_workspaces"))

        self.lbl_sec_limits.setText(translator.text("settings.form.section_limits"))
        self.lbl_form_timeout.setText(translator.text("settings.form.timeout_seconds"))
        self.lbl_form_concurrency.setText(translator.text("settings.form.max_concurrency"))
        self.lbl_form_max_output.setText(translator.text("settings.form.max_output_bytes"))
        self.btn_save_form.setText(f"💾  {translator.text('settings.form.save')}")
        self.btn_reset_form.setText(f"🔄  {translator.text('settings.form.reset')}")

        # Raw editor
        env_path = self.repo_root / ".env"
        self.lbl_raw_path.setText(translator.text("settings.raw.target_file", path=str(env_path)))
        self.lbl_raw_notice.setText(translator.text("settings.raw.notice"))
        self.btn_save_raw.setText(f"💾  {translator.text('settings.raw.save')}")
        self.btn_reload_raw.setText(f"🔄  {translator.text('settings.raw.reload')}")
        self.btn_validate_env.setText(f"✨  {translator.text('settings.raw.validate')}")
        self.btn_load_example.setText(f"📋  {translator.text('settings.raw.load_example')}")

        # System info
        self.info_heading.setText(translator.text("settings.system_info"))
        self.info_desc.setText(translator.text("settings.system_desc"))

        # Metric cells
        self.metric_theme.label.setText(translator.text("settings.active_theme"))
        self.metric_lang.label.setText(translator.text("settings.active_language"))
        self.metric_ver.label.setText(translator.text("settings.app_version"))
        self.metric_env.label.setText(translator.text("settings.metric_config"))

        theme_key = f"settings.theme_{self.current_theme}"
        theme_text = translator.text(theme_key)
        if theme_text == theme_key:
            theme_text = self.current_theme.replace("_", " ").title()
        lang_text = (
            translator.text("language.vi")
            if self.translator.language == "vi"
            else translator.text("language.en")
        )
        self.metric_theme.value.setText(theme_text)
        self.metric_lang.value.setText(lang_text)

        self.ws_row.setText(f"Workspace: {self.get_workspace() or '~'}")
        self._update_button_states()
