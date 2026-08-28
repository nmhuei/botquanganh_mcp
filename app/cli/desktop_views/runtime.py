"""Runtime-state presentation for the native desktop control centre."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.cli.desktop_views.i18n import DesktopTranslator, TranslationBindings
from app.cli.desktop_views.theme import PALETTE

BACKEND_ALIVE_BADGE = ("backend: ● alive", PALETTE["success"])
BACKEND_DOWN_BADGE = ("backend: ○ down", PALETTE["text_subtle"])


@dataclass(frozen=True)
class RuntimePresentation:
    """All values rendered by the desktop Runtime surface."""

    status: str
    color: str
    summary: str
    bridge: str
    server: str
    tunnel: str
    endpoint: str
    authentication: str


def runtime_presentation(
    data: dict[str, Any], translator: DesktopTranslator | None = None
) -> RuntimePresentation:
    """Normalize a lifecycle status response for the desktop view."""
    translator = translator or DesktopTranslator()
    server = data.get("server") or {}
    tunnel = data.get("tunnel") or {}
    if data.get("ok"):
        status, color, summary = (
            translator.text("status.ready"),
            PALETTE["success"],
            translator.text("runtime.ready_summary"),
        )
    elif server.get("running") or tunnel.get("running"):
        status, color, summary = (
            translator.text("status.needs_attention"),
            PALETTE["warning"],
            translator.text("runtime.attention_summary"),
        )
    else:
        status, color, summary = (
            translator.text("status.stopped"),
            PALETTE["text_subtle"],
            translator.text("runtime.stopped_summary"),
        )
    return RuntimePresentation(
        status=status,
        color=color,
        summary=summary,
        bridge=str(data.get("bridge", "unknown")),
        server=translator.text("status.running")
        if server.get("running")
        else translator.text("status.stopped_value"),
        tunnel=translator.text("status.running")
        if tunnel.get("running")
        else translator.text("status.stopped_value"),
        endpoint=str(
            data.get("url")
            or data.get("last_known_url")
            or translator.text("status.not_available")
        ),
        authentication=translator.text("status.enabled")
        if data.get("auth_required")
        else translator.text("status.disabled"),
    )


class RuntimeView:
    """Owns runtime display variables while the dashboard owns lifecycle actions."""

    def __init__(
        self,
        tk: Any,
        initial_message: str = "",
        translator: DesktopTranslator | None = None,
    ) -> None:
        self.translator = translator or DesktopTranslator()
        self.bindings = TranslationBindings(self.translator)
        self.values = {
            key: tk.StringVar(value=self.translator.text("status.not_available"))
            for key in ("bridge", "server", "tunnel", "endpoint", "authentication")
        }
        self.status_var = tk.StringVar(value=self.translator.text("status.loading"))
        self.backend_var = tk.StringVar(value="backend: …")
        self.message_var = tk.StringVar(value=initial_message)
        self.action_buttons: list[Any] = []
        self.latest_data: dict[str, Any] | None = None

    def render(self, data: dict[str, Any]) -> RuntimePresentation:
        """Apply a status response and return its normalized presentation."""
        self.latest_data = dict(data)
        presentation = runtime_presentation(data, self.translator)
        self.status_var.set(presentation.status)
        self.backend_var.set(
            self.translator.text("backend.alive")
            if (data.get("server") or {}).get("running")
            else self.translator.text("backend.down")
        )
        self.values["bridge"].set(presentation.bridge)
        self.values["server"].set(presentation.server)
        self.values["tunnel"].set(presentation.tunnel)
        self.values["endpoint"].set(presentation.endpoint)
        self.values["authentication"].set(presentation.authentication)
        return presentation

    def set_translator(self, translator: DesktopTranslator) -> None:
        """Relabel the existing Runtime surface without resetting its state."""
        self.translator = translator
        self.bindings.set_translator(translator)
        if self.latest_data is not None:
            self.render(self.latest_data)
        else:
            self.status_var.set(translator.text("status.loading"))

    def set_message(self, text: str) -> None:
        self.message_var.set(text)

    def build(
        self,
        *,
        ttk: Any,
        parent: Any,
        workspace_var: Any,
        on_copy_endpoint: Any,
        on_choose_workspace: Any,
        on_apply_workspace: Any,
    ) -> None:
        """Attach the Runtime property grid without reaching into the dashboard."""
        fields = ttk.LabelFrame(parent, padding=14)
        self.bindings.bind(fields, "field.runtime_status")
        fields.pack(fill="both", expand=True)
        fields.columnconfigure(1, weight=1)
        rows = (
            ("field.mcp_bridge", "bridge"),
            ("field.server", "server"),
            ("field.tunnel", "tunnel"),
            ("field.endpoint", "endpoint"),
            ("field.authentication", "authentication"),
            ("field.workspace", "workspace"),
        )
        for index, (label_key, key) in enumerate(rows):
            label = ttk.Label(fields, style="FieldName.TLabel")
            self.bindings.bind(label, label_key)
            label.grid(
                row=index, column=0, sticky="nw", padx=(0, 18), pady=5
            )
            value = (
                ttk.Entry(fields, textvariable=workspace_var, state="readonly", width=58)
                if key == "workspace"
                else ttk.Label(fields, textvariable=self.values[key], wraplength=500)
            )
            value.grid(row=index, column=1, sticky="ew" if key == "workspace" else "w", pady=5)
            if key == "endpoint":
                copy_button = ttk.Button(fields, command=on_copy_endpoint)
                self.bindings.bind(copy_button, "action.copy")
                copy_button.grid(
                    row=index, column=2, sticky="e", padx=(10, 0), pady=5
                )
            if key == "workspace":
                choose_button = ttk.Button(fields, command=on_choose_workspace)
                self.bindings.bind(choose_button, "action.choose_folder")
                choose_button.grid(
                    row=index, column=2, sticky="e", padx=(10, 0), pady=5
                )
                apply_button = ttk.Button(fields, command=on_apply_workspace)
                self.bindings.bind(apply_button, "action.apply")
                apply_button.grid(
                    row=index, column=3, sticky="e", padx=(8, 0), pady=5
                )
                self.action_buttons.append(apply_button)

    def set_busy(self, busy: bool) -> None:
        """Enable or disable only the actions registered by this view."""
        for button in self.action_buttons:
            button.state(["disabled"] if busy else ["!disabled"])
