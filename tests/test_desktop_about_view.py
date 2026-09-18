"""Tests for the desktop AboutView component."""

import pytest

from app.cli.desktop_views.about import (
    AboutView,
    CHATGPT_PROMPT_TEMPLATE_EN,
    CHATGPT_PROMPT_TEMPLATE_VI,
    CHATGPT_WEB_GUIDE_EN,
    CHATGPT_WEB_GUIDE_VI,
    README_TOOLS_EN,
    README_TOOLS_VI,
)
from app.cli.desktop_views.i18n import DesktopTranslator


class DummyWidget:
    def __init__(self, parent=None, **kwargs):
        self.parent = parent
        self.configured = dict(kwargs)
        self.grid_calls = []
        self.pack_calls = []

    def configure(self, **kwargs):
        self.configured.update(kwargs)

    def grid(self, **kwargs):
        self.grid_calls.append(kwargs)

    def pack(self, **kwargs):
        self.pack_calls.append(kwargs)

    def columnconfigure(self, *args, **kwargs):
        pass

    def rowconfigure(self, *args, **kwargs):
        pass


class DummyButton(DummyWidget):
    def invoke(self):
        cmd = self.configured.get("command")
        if cmd:
            return cmd()


class DummyLabel(DummyWidget):
    pass


class DummyFrame(DummyWidget):
    pass


class DummyLabelFrame(DummyWidget):
    pass


class DummyText(DummyWidget):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.content = ""

    def get(self, start="1.0", end="end-1c"):
        return self.content

    def delete(self, start="1.0", end="end"):
        self.content = ""

    def insert(self, index, text):
        self.content += text

    def yview(self):
        return (0.0, 1.0)

    def yview_moveto(self, pos):
        pass

    def xview(self):
        return (0.0, 1.0)

    def xview_moveto(self, pos):
        pass

    def bind(self, event, cb):
        pass


class DummyNotebook(DummyWidget):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.tabs = []
        self.tab_labels = {}
        self.selected_tab = None

    def add(self, frame, text=""):
        self.tabs.append(frame)
        self.tab_labels[str(frame)] = text
        if self.selected_tab is None:
            self.selected_tab = str(frame)

    def select(self, frame=None):
        if frame is not None:
            self.selected_tab = str(frame)
        return self.selected_tab

    def tab(self, frame, text=None, **kwargs):
        if text is not None:
            self.tab_labels[str(frame)] = text
        return {"text": self.tab_labels.get(str(frame), "")}


class DummyScrollbar(DummyWidget):
    def set(self, *args):
        pass


class DummyTtk:
    def Frame(self, parent=None, **kwargs):
        return DummyFrame(parent, **kwargs)

    def LabelFrame(self, parent=None, **kwargs):
        return DummyLabelFrame(parent, **kwargs)

    def Label(self, parent=None, **kwargs):
        return DummyLabel(parent, **kwargs)

    def Button(self, parent=None, **kwargs):
        return DummyButton(parent, **kwargs)

    def Notebook(self, parent=None, **kwargs):
        return DummyNotebook(parent, **kwargs)

    def Scrollbar(self, parent=None, **kwargs):
        return DummyScrollbar(parent, **kwargs)


class DummyRoot:
    def __init__(self):
        self.clipboard = ""

    def clipboard_clear(self):
        self.clipboard = ""

    def clipboard_append(self, text):
        self.clipboard += text

    def update_idletasks(self):
        pass


class DummyTk:
    Text = DummyText


def test_about_view_builds_and_populates_vietnamese_content():
    root = DummyRoot()
    tk = DummyTk()
    ttk = DummyTtk()
    parent = DummyFrame()
    messages = []

    def on_message(kind, text):
        messages.append((kind, text))

    translator = DesktopTranslator("vi")
    view = AboutView(
        root=root,
        tk=tk,
        ttk=ttk,
        parent=parent,
        on_message=on_message,
        on_copy_endpoint=lambda: root.clipboard_append("https://custom.mcp/mcp"),
        translator=translator,
    )

    assert view.inspector is not None
    assert "readme_tools" in view.inspector.text_by_key
    assert "chatgpt_web" in view.inspector.text_by_key

    # Check content in Vietnamese
    readme_text = view.inspector.text_by_key["readme_tools"].get()
    chatgpt_text = view.inspector.text_by_key["chatgpt_web"].get()

    assert "BOTQUANGANH HOST MCP" in readme_text
    assert "health_check" in readme_text
    assert "host_workspace_bind" in readme_text
    assert "HƯỚNG DẪN CHI TIẾT KẾT NỐI" in chatgpt_text
    assert "ATTRIBUTION_MODE=enforce" in chatgpt_text
    assert "E6" in chatgpt_text


def test_about_view_builds_and_populates_english_content():
    root = DummyRoot()
    tk = DummyTk()
    ttk = DummyTtk()
    parent = DummyFrame()
    messages = []

    translator = DesktopTranslator("en")
    view = AboutView(
        root=root,
        tk=tk,
        ttk=ttk,
        parent=parent,
        on_message=lambda k, m: messages.append((k, m)),
        translator=translator,
    )

    readme_text = view.inspector.text_by_key["readme_tools"].get()
    chatgpt_text = view.inspector.text_by_key["chatgpt_web"].get()

    assert "TOOL CATALOG & SPECIFICATION" in readme_text
    assert "health_check" in readme_text
    assert "STEP-BY-STEP INTEGRATION GUIDE" in chatgpt_text
    assert "MANDATORY 3-STEP HANDSHAKE" in chatgpt_text


def test_about_view_switch_language_updates_content_and_labels():
    root = DummyRoot()
    tk = DummyTk()
    ttk = DummyTtk()
    parent = DummyFrame()
    messages = []

    view = AboutView(
        root=root,
        tk=tk,
        ttk=ttk,
        parent=parent,
        on_message=lambda k, m: messages.append((k, m)),
        translator=DesktopTranslator("en"),
    )

    assert "TOOL CATALOG & SPECIFICATION" in view.inspector.text_by_key["readme_tools"].get()

    # Switch to Vietnamese
    view.set_translator(DesktopTranslator("vi"))
    assert "DANH MỤC VÀ TÀI LIỆU CÔNG CỤ" in view.inspector.text_by_key["readme_tools"].get()
    assert "HƯỚNG DẪN CHI TIẾT" in view.inspector.text_by_key["chatgpt_web"].get()


def test_about_view_copy_chatgpt_prompt_copies_to_clipboard():
    root = DummyRoot()
    tk = DummyTk()
    ttk = DummyTtk()
    parent = DummyFrame()
    messages = []

    view = AboutView(
        root=root,
        tk=tk,
        ttk=ttk,
        parent=parent,
        on_message=lambda k, m: messages.append((k, m)),
        translator=DesktopTranslator("vi"),
    )

    view.copy_chatgpt_prompt()
    assert root.clipboard == CHATGPT_PROMPT_TEMPLATE_VI
    assert len(messages) == 1
    assert messages[0][0] == "success"


def test_about_view_copy_endpoint_fallback():
    root = DummyRoot()
    tk = DummyTk()
    ttk = DummyTtk()
    parent = DummyFrame()
    messages = []

    view = AboutView(
        root=root,
        tk=tk,
        ttk=ttk,
        parent=parent,
        on_message=lambda k, m: messages.append((k, m)),
        get_endpoint=lambda: "https://demo.trycloudflare.com/mcp",
        translator=DesktopTranslator("vi"),
    )

    view.copy_endpoint()
    assert root.clipboard == "https://demo.trycloudflare.com/mcp"
    assert messages == [("success", "Đã sao chép URL connector MCP vào clipboard.")]
