from app.cli.desktop_views.runtime import RuntimePresentation, RuntimeView, runtime_presentation
from app.cli.desktop_views.i18n import DesktopTranslator


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
        color="#4ade80",
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


def test_runtime_view_registers_workspace_apply_action_for_busy_state():
    class Variable:
        def __init__(self, value=""):
            self.value = value

        def set(self, value):
            self.value = value

        def get(self):
            return self.value

    class Widget:
        def __init__(self):
            self.state_calls = []

        def pack(self, **_kwargs):
            pass

        def grid(self, **_kwargs):
            pass

        def grid_remove(self):
            pass

        def columnconfigure(self, *_args, **_kwargs):
            pass

        def rowconfigure(self, *_args, **_kwargs):
            pass

        def configure(self, **_kwargs):
            pass

        def state(self, value):
            self.state_calls.append(value)

    class Ttk:
        def __init__(self):
            self.buttons = []

        def Frame(self, *_args, **_kwargs):
            return Widget()

        def LabelFrame(self, *_args, **_kwargs):
            return Widget()

        def Label(self, *_args, **_kwargs):
            return Widget()

        def Entry(self, *_args, **_kwargs):
            return Widget()

        def Button(self, *_args, **_kwargs):
            button = Widget()
            self.buttons.append(button)
            return button

    ttk = Ttk()
    view = RuntimeView(type("Tk", (), {"StringVar": Variable}), "ready")
    view.build(
        ttk=ttk,
        parent=Widget(),
        workspace_var=Variable(),
        on_copy_endpoint=lambda: None,
        on_choose_workspace=lambda: None,
        on_apply_workspace=lambda: None,
    )
    view.set_busy(True)

    assert ttk.buttons[-1].state_calls == [["disabled"]]
