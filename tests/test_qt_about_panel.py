"""Tests for the QtAboutPanel and about_html builders."""

from __future__ import annotations

import pytest
from PySide6 import QtCore, QtWidgets

from app.cli.desktop_qt.about import QtAboutPanel
from app.cli.desktop_qt.about_html import build_chatgpt_guide_html, build_readme_html
from app.cli.desktop_views.about import (
    CHATGPT_PROMPT_TEMPLATE_EN,
    CHATGPT_PROMPT_TEMPLATE_VI,
    CHATGPT_WEB_GUIDE_EN,
    CHATGPT_WEB_GUIDE_VI,
    README_TOOLS_EN,
    README_TOOLS_VI,
)
from app.cli.desktop_views.i18n import DesktopTranslator


import os

@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


def test_about_html_builders_render_expected_sections():
    readme_vi = build_readme_html(is_vi=True)
    assert "17 TOOLS HOẠT ĐỘNG" in readme_vi
    assert "health_check" in readme_vi
    assert "host_workspace_bind" in readme_vi
    assert "ctf_triage_artifact" in readme_vi
    assert "host_replace_in_file" in readme_vi

    readme_en = build_readme_html(is_vi=False)
    assert "17 TOOLS ACTIVE" in readme_en
    assert "health_check" in readme_en
    assert "host_workspace_bind" in readme_en

    guide_vi = build_chatgpt_guide_html(is_vi=True)
    assert "HƯỚNG DẪN TÍCH HỢP TOÀN DIỆN VỚI CHATGPT WEB" in guide_vi
    assert "CLOUDFLARE TUNNEL" in guide_vi
    assert "host_workspace_bind" in guide_vi
    assert "E6: BIND_REQUIRED" in guide_vi

    guide_en = build_chatgpt_guide_html(is_vi=False)
    assert "END-TO-END INTEGRATION GUIDE FOR CHATGPT WEB" in guide_en
    assert "CLOUDFLARE TUNNEL" in guide_en
    assert "E6: BIND_REQUIRED" in guide_en


def test_qt_about_panel_builds_and_switches_languages(qapp):
    translator = DesktopTranslator("vi")
    messages = []
    endpoint_called = []

    panel = QtAboutPanel(
        QtCore,
        QtWidgets,
        translator,
        on_copy_endpoint=lambda: endpoint_called.append(True),
        on_message=lambda kind, msg: messages.append((kind, msg)),
    )

    assert panel.widget is not None
    assert panel.tabs.count() == 2
    assert panel.metric_tools.value.text() == "17 Tools Sẵn Sàng"
    assert panel.metric_guard.value.text() == "Guarded & Enforce"

    # Verify HTML is set
    assert "health_check" in panel.readme_view.toPlainText()
    assert "chatgpt" in panel.chatgpt_view.toPlainText().lower() or "cloudflare" in panel.chatgpt_view.toPlainText().lower()

    # Switch language to English
    en_translator = DesktopTranslator("en")
    panel.set_translator(en_translator)

    assert panel.metric_tools.value.text() == "17 Tools Active"
    assert panel.tabs.tabText(0) == "README Tools"
    assert panel.tabs.tabText(1) == "How to use in ChatGPT Web"

    # Test copy endpoint
    panel.copy_endpoint()
    assert endpoint_called == [True]

    # Test copy prompt
    clipboard = QtWidgets.QApplication.clipboard()
    panel.copy_chatgpt_prompt()
    assert CHATGPT_PROMPT_TEMPLATE_EN in clipboard.text()
    assert any(k == "success" for k, _ in messages)

    # Test copy active section
    panel.tabs.setCurrentIndex(0)
    panel.copy_active_section()
    assert README_TOOLS_EN in clipboard.text()

    panel.tabs.setCurrentIndex(1)
    panel.copy_active_section()
    assert CHATGPT_WEB_GUIDE_EN in clipboard.text()
