"""PySide About panel showing README tools and ChatGPT Web guide with rich Cyberpunk styling."""

from __future__ import annotations

from typing import Any, Callable

from app.cli.desktop_qt.about_html import build_chatgpt_guide_html, build_readme_html
from app.cli.desktop_qt.theme import COLORS, LAYOUT
from app.cli.desktop_qt.widgets import MetricCell, SectionHeading, apply_button_variant
from app.cli.desktop_views.about import (
    CHATGPT_PROMPT_TEMPLATE_EN,
    CHATGPT_PROMPT_TEMPLATE_VI,
    CHATGPT_WEB_GUIDE_EN,
    CHATGPT_WEB_GUIDE_VI,
    README_TOOLS_EN,
    README_TOOLS_VI,
)
from app.cli.desktop_views.i18n import DesktopTranslator


class QtAboutPanel:
    """Render tools documentation and ChatGPT Web step-by-step guide."""

    def __init__(
        self,
        QtCore: Any,
        QtWidgets: Any,
        translator: DesktopTranslator,
        *,
        on_copy_endpoint: Callable[[], None] | None = None,
        get_endpoint: Callable[[], str] | None = None,
        on_message: Callable[[str, str], None] | None = None,
    ) -> None:
        self.QtCore = QtCore
        self.QtWidgets = QtWidgets
        self.translator = translator
        self.on_copy_endpoint = on_copy_endpoint
        self.get_endpoint = get_endpoint
        self.on_message = on_message or (lambda kind, msg: None)

        self.widget = QtWidgets.QWidget()
        self.widget.setObjectName("aboutPage")
        layout = QtWidgets.QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(LAYOUT["space_md"])

        # 1. Header Frame with Title & Action Buttons
        self.header_frame = QtWidgets.QFrame()
        self.header_frame.setObjectName("aboutHeaderFrame")
        header_layout = QtWidgets.QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(LAYOUT["space_sm"])

        self.heading = SectionHeading(
            QtWidgets,
            translator.text("about.title"),
            translator.text("about.subtitle"),
        )
        self.heading.widget.setObjectName("aboutHeader")
        header_layout.addWidget(self.heading.widget)
        header_layout.addStretch(1)

        self.copy_endpoint_button = QtWidgets.QPushButton(
            translator.text("about.action.copy_endpoint")
        )
        self.copy_endpoint_button.setProperty("role", "compactAction")
        apply_button_variant(self.copy_endpoint_button, "primary")
        self.copy_endpoint_button.clicked.connect(self.copy_endpoint)
        header_layout.addWidget(self.copy_endpoint_button)

        self.copy_prompt_button = QtWidgets.QPushButton(
            translator.text("about.action.copy_prompt")
        )
        self.copy_prompt_button.setProperty("role", "compactAction")
        apply_button_variant(self.copy_prompt_button, "secondary")
        self.copy_prompt_button.clicked.connect(self.copy_chatgpt_prompt)
        header_layout.addWidget(self.copy_prompt_button)

        self.copy_section_button = QtWidgets.QPushButton(
            translator.text("about.action.copy_section")
        )
        self.copy_section_button.setProperty("role", "compactAction")
        apply_button_variant(self.copy_section_button, "secondary")
        self.copy_section_button.clicked.connect(self.copy_active_section)
        header_layout.addWidget(self.copy_section_button)

        layout.addWidget(self.header_frame)

        # 2. Metric Strip (Command Center Summary Cards)
        self.metric_strip = QtWidgets.QFrame()
        self.metric_strip.setObjectName("metricStrip")
        self.metric_strip.setProperty("role", "card")
        self.metric_strip.setMinimumHeight(76)
        metric_layout = QtWidgets.QHBoxLayout(self.metric_strip)
        metric_layout.setContentsMargins(12, 8, 12, 8)
        metric_layout.setSpacing(8)

        self.metric_tools = MetricCell(QtWidgets, "TOTAL TOOLS", "17 Tools Active")
        self.metric_proto = MetricCell(QtWidgets, "PROTOCOL", "Streamable HTTP")
        self.metric_guard = MetricCell(QtWidgets, "GUARD POLICY", "Guarded + Enforce")
        self.metric_target = MetricCell(QtWidgets, "AI TARGET", "ChatGPT Web (/mcp)")

        # Style metric values
        self.metric_tools.value.setStyleSheet(f"color: {COLORS['lime']}; font-weight: 700; font-size: 14px;")
        self.metric_proto.value.setStyleSheet(f"color: {COLORS['text']}; font-weight: 700; font-size: 14px;")
        self.metric_guard.value.setStyleSheet(f"color: {COLORS['success']}; font-weight: 700; font-size: 14px;")
        self.metric_target.value.setStyleSheet(f"color: {COLORS['warning']}; font-weight: 700; font-size: 14px;")

        metric_layout.addWidget(self.metric_tools.widget)
        metric_layout.addWidget(self.metric_proto.widget)
        metric_layout.addWidget(self.metric_guard.widget)
        metric_layout.addWidget(self.metric_target.widget)

        layout.addWidget(self.metric_strip)

        # 3. Main Tabs with Rich QTextBrowser
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setObjectName("aboutTabs")

        self.readme_view = QtWidgets.QTextBrowser()
        self.readme_view.setObjectName("aboutReadmeView")
        self.readme_view.setReadOnly(True)
        self.readme_view.setOpenExternalLinks(True)

        self.chatgpt_view = QtWidgets.QTextBrowser()
        self.chatgpt_view.setObjectName("aboutChatgptView")
        self.chatgpt_view.setReadOnly(True)
        self.chatgpt_view.setOpenExternalLinks(True)

        self.tabs.addTab(self.readme_view, translator.text("about.tab.readme_tools"))
        self.tabs.addTab(self.chatgpt_view, translator.text("about.tab.chatgpt_web"))

        layout.addWidget(self.tabs, 1)
        self._refresh_content()

    def set_translator(self, translator: DesktopTranslator) -> None:
        self.translator = translator
        self.heading.title_label.setText(translator.text("about.title"))
        self.heading.eyebrow_label.setText(translator.text("about.subtitle"))
        self.copy_endpoint_button.setText(translator.text("about.action.copy_endpoint"))
        self.copy_prompt_button.setText(translator.text("about.action.copy_prompt"))
        self.copy_section_button.setText(translator.text("about.action.copy_section"))
        self.tabs.setTabText(0, translator.text("about.tab.readme_tools"))
        self.tabs.setTabText(1, translator.text("about.tab.chatgpt_web"))
        self._refresh_content()

    def _refresh_content(self) -> None:
        is_vi = self.translator.language == "vi"

        if is_vi:
            self.metric_tools.label.setText("TỔNG CÔNG CỤ")
            self.metric_tools.value.setText("17 Tools Sẵn Sàng")
            self.metric_proto.label.setText("GIAO THỨC TRUYỀN TẢI")
            self.metric_proto.value.setText("Streamable HTTP")
            self.metric_guard.label.setText("CHÍNH SÁCH BẢO MẬT")
            self.metric_guard.value.setText("Guarded & Enforce")
            self.metric_target.label.setText("KẾT NỐI AI")
            self.metric_target.value.setText("ChatGPT Web (/mcp)")
        else:
            self.metric_tools.label.setText("TOTAL TOOLS")
            self.metric_tools.value.setText("17 Tools Active")
            self.metric_proto.label.setText("PROTOCOL")
            self.metric_proto.value.setText("Streamable HTTP")
            self.metric_guard.label.setText("GUARD POLICY")
            self.metric_guard.value.setText("Guarded & Enforce")
            self.metric_target.label.setText("AI TARGET")
            self.metric_target.value.setText("ChatGPT Web (/mcp)")

        readme_html = build_readme_html(is_vi)
        chatgpt_html = build_chatgpt_guide_html(is_vi)

        readme_pos = self.readme_view.verticalScrollBar().value()
        self.readme_view.setHtml(readme_html)
        self.readme_view.verticalScrollBar().setValue(readme_pos)

        chatgpt_pos = self.chatgpt_view.verticalScrollBar().value()
        self.chatgpt_view.setHtml(chatgpt_html)
        self.chatgpt_view.verticalScrollBar().setValue(chatgpt_pos)

    def copy_endpoint(self) -> None:
        if self.on_copy_endpoint is not None:
            self.on_copy_endpoint()
            return
        url = self.get_endpoint() if self.get_endpoint is not None else ""
        if not url:
            self.on_message("warn", self.translator.text("message.no_endpoint"))
            return
        clipboard = self.QtWidgets.QApplication.clipboard()
        if clipboard:
            clipboard.setText(url)
        self.on_message("success", self.translator.text("about.copied_endpoint"))

    def copy_chatgpt_prompt(self) -> None:
        is_vi = self.translator.language == "vi"
        prompt = CHATGPT_PROMPT_TEMPLATE_VI if is_vi else CHATGPT_PROMPT_TEMPLATE_EN
        clipboard = self.QtWidgets.QApplication.clipboard()
        if clipboard:
            clipboard.setText(prompt)
        self.on_message("success", self.translator.text("about.copied_prompt"))

    def copy_active_section(self) -> None:
        current_index = self.tabs.currentIndex()
        active_view = self.readme_view if current_index == 0 else self.chatgpt_view
        cursor = active_view.textCursor()
        if cursor.hasSelection():
            text = cursor.selectedText()
        else:
            is_vi = self.translator.language == "vi"
            if current_index == 0:
                text = README_TOOLS_VI if is_vi else README_TOOLS_EN
            else:
                text = CHATGPT_WEB_GUIDE_VI if is_vi else CHATGPT_WEB_GUIDE_EN

        clipboard = self.QtWidgets.QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
        self.on_message("success", self.translator.text("about.copied_section"))
