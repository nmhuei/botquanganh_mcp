from app.cli.desktop_views.runtime import RuntimePresentation, RuntimeView, runtime_presentation
from app.cli.desktop_views.i18n import DesktopTranslator
from app.cli.desktop_views.theme import PALETTE


def test_runtime_presentation_uses_selected_language_without_changing_data():
    data = {
        "ok": True,
        "server": {"running": True},
        "tunnel": {"running": True},
    }

    assert runtime_presentation(data, DesktopTranslator("en")).status == "Ready"
    assert runtime_presentation(data, DesktopTranslator("vi")).status == "Sẵn sàng"


def test_runtime_presentation_normalizes_live_runtime_fields():
    presentation = runtime_presentation(
        {
            "ok": True,
            "bridge": "ready",
            "server": {"running": True},
            "tunnel": {"running": True},
            "url": "https://example.test/mcp",
            "auth_required": True,
        }
    )

    assert presentation == RuntimePresentation(
        status="Ready",
        color=PALETTE["success"],
        summary="MCP bridge and Cloudflare tunnel are running.",
        bridge="ready",
        server="running",
        tunnel="running",
        endpoint="https://example.test/mcp",
        authentication="enabled",
    )


def test_runtime_view_updates_only_its_registered_action_buttons():
    class Variable:
        def __init__(self, value=""):
            self.value = value

        def set(self, value):
            self.value = value

        def get(self):
            return self.value

    class Button:
        def __init__(self):
            self.calls = []

        def state(self, value):
            self.calls.append(value)

    view = RuntimeView(type("Tk", (), {"StringVar": Variable}), "ready")
    button = Button()
    view.action_buttons.append(button)

    view.set_busy(True)
    view.set_busy(False)

    assert button.calls == [["disabled"], ["!disabled"]]


def test_runtime_view_builds_service_cards_and_registers_runtime_actions_for_busy_state():
    """Dropping a lifecycle control from the worker lock must fail this test."""
    class Variable:
        def __init__(self, value=""):
            self.value = value

        def set(self, value):
            self.value = value

        def get(self):
            return self.value

    class Widget:
        def __init__(self, parent=None, **kwargs):
            self.parent = parent
            self.options = dict(kwargs)
            self.state_calls = []
            self.configure_calls = []

        def pack(self, **_kwargs):
            pass

        def grid(self, **_kwargs):
            pass

        def columnconfigure(self, *_args, **_kwargs):
            pass

        def configure(self, **kwargs):
            self.options.update(kwargs)
            self.configure_calls.append(kwargs)

        def state(self, value):
            self.state_calls.append(value)

    class Ttk:
        def __init__(self):
            self.widgets = []
            self.buttons = []
            self.button_styles = []
            self.button_commands = []
            self.frames = []
            self.label_frames = []
            self.label_frame_styles = []

        def _widget(self, kind, args, kwargs):
            widget = Widget(args[0] if args else None, **kwargs)
            widget.kind = kind
            self.widgets.append(widget)
            return widget

        def LabelFrame(self, *args, **kwargs):
            widget = self._widget("LabelFrame", args, kwargs)
            self.label_frames.append(widget)
            self.label_frame_styles.append(widget.options.get("style"))
            return widget

        def Frame(self, *args, **kwargs):
            widget = self._widget("Frame", args, kwargs)
            self.frames.append(widget)
            return widget

        def Label(self, *args, **kwargs):
            return self._widget("Label", args, kwargs)

        def Entry(self, *args, **kwargs):
            return self._widget("Entry", args, kwargs)

        def Button(self, *args, **kwargs):
            button = self._widget("Button", args, kwargs)
            self.buttons.append(button)
            self.button_styles.append(button.options.get("style"))
            self.button_commands.append(button.options.get("command"))
            return button

    ttk = Ttk()
    view = RuntimeView(type("Tk", (), {"StringVar": Variable}), "ready")
    workspace_var = Variable()
    callbacks = [lambda: None for _ in range(7)]
    view.build(
        ttk=ttk,
        parent=Widget(),
        workspace_var=workspace_var,
        on_copy_endpoint=callbacks[0],
        on_choose_workspace=callbacks[1],
        on_apply_workspace=callbacks[2],
        on_start=callbacks[3],
        on_stop=callbacks[4],
        on_restart=callbacks[5],
        on_refresh=callbacks[6],
    )
    view.set_busy(True)

    assert ttk.label_frame_styles == ["RuntimeCard.TLabelframe"] * 3
    buttons_by_text = {button.options["text"]: button for button in ttk.buttons}
    expected_actions = (
        ("Start", "Primary.TButton", callbacks[3]),
        ("Stop", "Danger.TButton", callbacks[4]),
        ("Restart", "Secondary.TButton", callbacks[5]),
        ("Refresh", "Secondary.TButton", callbacks[6]),
        ("Apply", "Primary.TButton", callbacks[2]),
    )
    for text, style, callback in expected_actions:
        assert buttons_by_text[text].options["style"] == style
        assert buttons_by_text[text].options["command"] is callback
    assert buttons_by_text["Copy"].options["command"] is callbacks[0]
    assert buttons_by_text["Choose folder…"].options["command"] is callbacks[1]
    expected_worker_actions = [buttons_by_text[text] for text, _style, _callback in expected_actions]
    assert view.action_buttons == expected_worker_actions
    assert buttons_by_text["Choose folder…"] not in view.action_buttons
    assert all(button.state_calls[-1] == ["disabled"] for button in expected_worker_actions)

    cards_by_title = {card.options["text"]: card for card in ttk.label_frames}
    expected_card_bindings = (
        ("MCP bridge", (view.values["bridge"], view.values["authentication"])),
        ("Server", (view.values["server"], view.values["endpoint"])),
        ("Cloudflare tunnel", (view.values["tunnel"], view.values["endpoint"])),
    )
    for title, expected_variables in expected_card_bindings:
        actual_variables = tuple(
            widget.options["textvariable"]
            for widget in ttk.widgets
            if widget.parent is cards_by_title[title]
            and "textvariable" in widget.options
        )
        assert actual_variables == expected_variables

    status_widgets = [
        widget for widget in ttk.widgets if widget.options.get("textvariable") is view.status_var
    ]
    summary_widgets = [
        widget for widget in ttk.widgets if widget.options.get("textvariable") is view.summary_var
    ]
    assert len(status_widgets) == len(summary_widgets) == 1
    assert status_widgets[0].parent is summary_widgets[0].parent
    assert summary_widgets[0].options["style"] == "SurfaceSubtle.TLabel"

    for title, expected_variables in expected_card_bindings:
        card = cards_by_title[title]
        card_labels = [widget for widget in ttk.widgets if widget.parent is card]
        assert card_labels[0].options["style"] == "RuntimeState.TLabel"
        assert card_labels[-1].options["style"] == "CardValue.TLabel"

    endpoint_rows = [
        frame
        for frame in ttk.frames
        if any(
            widget.parent is frame and widget.options.get("text") == "Endpoint"
            for widget in ttk.widgets
        )
    ]
    assert len(endpoint_rows) == 1
    assert [
        widget.options["textvariable"]
        for widget in ttk.widgets
        if widget.parent is endpoint_rows[0] and "textvariable" in widget.options
    ] == [view.values["endpoint"]]

    workspace_entries = [
        widget
        for widget in ttk.widgets
        if widget.kind == "Entry" and widget.options.get("textvariable") is workspace_var
    ]
    assert len(workspace_entries) == 1
    assert workspace_entries[0].parent.options.get("style") == "Surface.TFrame"
