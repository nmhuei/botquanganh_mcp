from app.cli.desktop_views.theme import PALETTE, InspectorTabs, apply_desktop_theme


def test_desktop_theme_configures_shared_semantic_widget_styles():
    class Style:
        def __init__(self):
            self.configured = {}
            self.mapped = {}
            self.theme = None

        def theme_use(self, name):
            self.theme = name

        def configure(self, name, **values):
            self.configured[name] = values

        def map(self, name, **values):
            self.mapped[name] = values

    class Root:
        def __init__(self):
            self.background = None

        def configure(self, **values):
            self.background = values["background"]

    style = Style()
    root = Root()

    apply_desktop_theme(style, root)

    assert style.theme == "clam"
    assert {"App.TFrame", "Table.Treeview", "Inspector.TNotebook", "Status.TLabel"} <= set(
        style.configured
    )
    assert "App.TNotebook" in style.mapped
    assert root.background == "#10151d"
    assert PALETTE["accent"] == "#60a5fa"
    assert PALETTE["running"] == "#2dd4bf"
    assert PALETTE["tab_background"] == "#070b0b"
    assert style.configured["Table.Treeview"]["rowheight"] == 30
    assert style.configured["App.TNotebook"]["background"] == "#070b0b"
    assert style.configured["App.TNotebook.Tab"]["foreground"] == PALETTE["tab_green"]
    assert style.configured["Inspector.TNotebook"]["background"] == PALETTE["tab_background"]
    assert style.configured["Inspector.TNotebook.Tab"]["foreground"] == PALETTE["tab_green"]
    assert style.mapped["Inspector.TNotebook.Tab"]["foreground"] == [
        ("selected", PALETTE["tab_green_active"]),
        ("active", PALETTE["tab_green_active"]),
    ]


def test_inspector_tabs_do_not_replace_unchanged_content_or_scroll_position():
    class Text:
        def __init__(self):
            self.content = ""
            self.delete_calls = 0
            self.scroll = 0.6

        def get(self, _start, _end):
            return self.content

        def yview(self):
            return (self.scroll, 0.8)

        def yview_moveto(self, value):
            self.scroll = value

        def configure(self, **_values):
            pass

        def delete(self, _start, _end):
            self.delete_calls += 1
            self.content = ""

        def insert(self, _start, text):
            self.content = text

    inspector = InspectorTabs.__new__(InspectorTabs)
    text = Text()
    inspector.text_by_key = {"metadata": text}

    inspector.set_content("metadata", "first")
    inspector.set_content("metadata", "first")

    assert text.content == "first"
    assert text.delete_calls == 1
    assert text.scroll == 0.6


def test_inspector_tabs_can_relabel_a_tab_without_recreating_it():
    class Notebook:
        def __init__(self):
            self.calls = []

        def tab(self, frame, **values):
            self.calls.append((frame, values))

    inspector = InspectorTabs.__new__(InspectorTabs)
    inspector.notebook = Notebook()
    inspector.frame_by_key = {"summary": "summary-frame"}

    inspector.set_tab_label("summary", "Tóm tắt")
    inspector.set_tab_label("unknown", "Ignored")

    assert inspector.notebook.calls == [("summary-frame", {"text": "Tóm tắt"})]


def test_inspector_tabs_copy_only_the_highlighted_text_for_ctrl_c():
    """The shortcut must not fall back to copying the full active tab."""

    class Root:
        def __init__(self):
            self.clipboard = ""
            self.updated = False

        def clipboard_clear(self):
            self.clipboard = ""

        def clipboard_append(self, value):
            self.clipboard = value

        def update_idletasks(self):
            self.updated = True

    class Text:
        def __init__(self):
            self.calls = []

        def tag_ranges(self, tag):
            assert tag == "sel"
            return ("2.0", "2.8")

        def get(self, start, end):
            self.calls.append((start, end))
            return "short id"

    inspector = InspectorTabs.__new__(InspectorTabs)
    inspector.root = Root()
    messages = []
    inspector.on_message = lambda kind, message: messages.append((kind, message))
    inspector.copy_selection_success_message = "Copied selected text."
    text = Text()

    assert inspector.copy_selection(text) == "break"
    assert text.calls == [("2.0", "2.8")]
    assert inspector.root.clipboard == "short id"
    assert inspector.root.updated is True
    assert messages == [("success", "Copied selected text.")]


def test_inspector_tabs_do_not_copy_the_whole_tab_when_ctrl_c_has_no_selection():
    class Text:
        def tag_ranges(self, tag):
            assert tag == "sel"
            return ()

        def get(self, _start, _end):
            raise AssertionError("the full tab must not be read without a selection")

    inspector = InspectorTabs.__new__(InspectorTabs)

    assert inspector.copy_selection(Text()) == "break"


def test_inspector_tabs_copy_tab_keeps_copying_the_entire_active_tab():
    class Root:
        def __init__(self):
            self.clipboard = ""

        def clipboard_clear(self):
            self.clipboard = ""

        def clipboard_append(self, value):
            self.clipboard = value

        def update_idletasks(self):
            pass

    class Text:
        def get(self, start, end):
            assert (start, end) == ("1.0", "end-1c")
            return "the complete active tab"

    inspector = InspectorTabs.__new__(InspectorTabs)
    inspector.root = Root()
    inspector.text_by_key = {"stdout": Text()}
    inspector.active_key = lambda: "stdout"
    messages = []
    inspector.on_message = lambda kind, message: messages.append((kind, message))
    inspector.copy_success_message = "Copied the visible inspector content to the clipboard."

    inspector.copy_active()

    assert inspector.root.clipboard == "the complete active tab"
    assert messages == [
        ("success", "Copied the visible inspector content to the clipboard.")
    ]


def test_desktop_theme_uses_system_fonts_and_visible_focus_styles():
    class Style:
        def __init__(self):
            self.configured = {}
            self.mapped = {}

        def theme_use(self, _name):
            pass

        def configure(self, name, **values):
            self.configured[name] = values

        def map(self, name, **values):
            self.mapped[name] = values

    class Root:
        def configure(self, **_values):
            pass

    style = Style()
    apply_desktop_theme(style, Root())

    assert style.configured["TLabel"]["font"] == "TkDefaultFont"
    assert style.configured["Header.TLabel"]["font"] == "TkHeadingFont"
    assert style.configured["Mono.TLabel"]["font"] == "TkFixedFont"
    assert ("focus", PALETTE["focus"]) in style.mapped["TEntry"]["bordercolor"]
    assert ("focus", PALETTE["focus"]) in style.mapped["TButton"]["bordercolor"]
    assert "LanguageActive.TButton" in style.configured
    assert "WarningBanner.TFrame" in style.configured
    assert "Feedback.TLabel" in style.configured


def test_desktop_palette_text_contrast_meets_normal_text_target():
    def rgb(hex_color):
        value = hex_color.lstrip("#")
        return tuple(int(value[index:index + 2], 16) / 255 for index in (0, 2, 4))

    def luminance(hex_color):
        channels = []
        for channel in rgb(hex_color):
            channels.append(
                channel / 12.92
                if channel <= 0.04045
                else ((channel + 0.055) / 1.055) ** 2.4
            )
        red, green, blue = channels
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    def ratio(foreground, background):
        high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
        return (high + 0.05) / (low + 0.05)

    assert ratio(PALETTE["text"], PALETTE["surface"]) >= 4.5
    assert ratio(PALETTE["text_muted"], PALETTE["app_background"]) >= 4.5
    assert ratio(PALETTE["tab_green"], PALETTE["tab_background"]) >= 4.5
