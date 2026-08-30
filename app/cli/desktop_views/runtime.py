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
    data: dict[str, Any],
    translator: DesktopTranslator | None = None,
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
        server=(
            translator.text("status.running")
            if server.get("running")
            else translator.text("status.stopped_value")
        ),
        tunnel=(
            translator.text("status.running")
            if tunnel.get("running")
            else translator.text("status.stopped_value")
        ),
        endpoint=str(
            data.get("url")
            or data.get("last_known_url")
            or translator.text("status.not_available")
        ),
        authentication=(
            translator.text("status.enabled")
            if data.get("auth_required")
            else translator.text("status.disabled")
        ),
    )


class RuntimeView:
    """Own the Runtime dashboard while the coordinator owns lifecycle execution."""

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
        self.auth_warning_var = tk.StringVar(
            value=self.translator.text("runtime.auth_warning")
        )
        self.action_buttons: list[Any] = []
        self.latest_data: dict[str, Any] | None = None
        self.auth_banner: Any = None

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
        self._render_auth_banner(bool(data.get("auth_required")))
        return presentation

    def _render_auth_banner(self, authentication_enabled: bool) -> None:
        if self.auth_banner is None:
            return
        try:
            if authentication_enabled:
                self.auth_banner.grid_remove()
            else:
                self.auth_banner.grid()
        except (AttributeError, RuntimeError):
            return

    def set_translator(self, translator: DesktopTranslator) -> None:
        """Relabel the existing Runtime surface without resetting its state."""
        self.translator = translator
        self.bindings.set_translator(translator)
        self.auth_warning_var.set(translator.text("runtime.auth_warning"))
        if self.latest_data is not None:
            self.render(self.latest_data)
        else:
            self.status_var.set(translator.text("status.loading"))

    def set_message(self, text: str) -> None:
        self.message_var.set(text)

    def _build_status_grid(self, ttk: Any, parent: Any) -> None:
        rows = (
            ("field.mcp_bridge", "bridge"),
            ("field.server", "server"),
            ("field.tunnel", "tunnel"),
            ("field.authentication", "authentication"),
        )
        for index, (label_key, key) in enumerate(rows):
            label = ttk.Label(parent, style="FieldName.TLabel")
            self.bindings.bind(label, label_key)
            label.grid(row=index, column=0, sticky="w", padx=(0, 18), pady=6)
            value = ttk.Label(parent, textvariable=self.values[key])
            value.grid(row=index, column=1, sticky="w", pady=6)

    def build(
        self,
        *,
        ttk: Any,
        parent: Any,
        workspace_var: Any,
        on_copy_endpoint: Any,
        on_choose_workspace: Any,
        on_apply_workspace: Any,
        on_start_service: Any = None,
        on_restart_bridge: Any = None,
    ) -> None:
        """Attach a professional Runtime dashboard with grouped responsibilities."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        self.auth_banner = ttk.Frame(
            parent,
            style="WarningBanner.TFrame",
            padding=(12, 8),
        )
        warning = ttk.Label(
            self.auth_banner,
            textvariable=self.auth_warning_var,
            style="WarningBanner.TLabel",
            wraplength=820,
        )
        warning.grid(row=0, column=0, sticky="w")
        self.auth_banner.columnconfigure(0, weight=1)
        self.auth_banner.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        content = ttk.Frame(parent, style="Surface.TFrame")
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        status = ttk.LabelFrame(content, padding=14)
        self.bindings.bind(status, "field.runtime_status")
        status.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 6))
        status.columnconfigure(1, weight=1)
        self._build_status_grid(ttk, status)

        connector = ttk.LabelFrame(content, padding=14)
        self.bindings.bind(connector, "runtime.connector")
        connector.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 6))
        connector.columnconfigure(0, weight=1)
        endpoint_label = ttk.Label(connector, style="FieldName.TLabel")
        self.bindings.bind(endpoint_label, "field.endpoint")
        endpoint_label.grid(row=0, column=0, sticky="w")
        endpoint = ttk.Label(
            connector,
            textvariable=self.values["endpoint"],
            style="Mono.TLabel",
            wraplength=430,
        )
        endpoint.grid(row=1, column=0, sticky="ew", pady=(6, 10))
        copy_button = ttk.Button(
            connector,
            command=on_copy_endpoint,
            style="Compact.TButton",
        )
        self.bindings.bind(copy_button, "action.copy")
        copy_button.grid(row=2, column=0, sticky="e")

        workspace = ttk.LabelFrame(content, padding=14)
        self.bindings.bind(workspace, "field.workspace")
        workspace.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=(6, 0))
        workspace.columnconfigure(0, weight=1)
        workspace_entry = ttk.Entry(
            workspace,
            textvariable=workspace_var,
            state="readonly",
        )
        workspace_entry.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 10),
        )
        choose_button = ttk.Button(
            workspace,
            command=on_choose_workspace,
            style="Compact.TButton",
        )
        self.bindings.bind(choose_button, "action.choose_folder")
        choose_button.grid(row=1, column=0, sticky="w")
        apply_button = ttk.Button(
            workspace,
            command=on_apply_workspace,
            style="Primary.TButton",
        )
        self.bindings.bind(apply_button, "action.apply")
        apply_button.grid(row=1, column=1, sticky="e", padx=(8, 0))
        self.action_buttons.append(apply_button)

        actions = ttk.LabelFrame(content, padding=14)
        self.bindings.bind(actions, "runtime.actions")
        actions.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=(6, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        action_help = ttk.Label(
            actions,
            style="SurfaceSubtle.TLabel",
            wraplength=430,
        )
        self.bindings.bind(action_help, "runtime.actions_help")
        action_help.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 12),
        )
        if on_start_service is not None:
            start_button = ttk.Button(
                actions,
                command=on_start_service,
                style="Primary.TButton",
            )
            self.bindings.bind(start_button, "action.start_adopt")
            start_button.grid(row=1, column=0, sticky="ew", padx=(0, 5))
            self.action_buttons.append(start_button)
        if on_restart_bridge is not None:
            restart_button = ttk.Button(
                actions,
                command=on_restart_bridge,
                style="Toolbar.TButton",
            )
            self.bindings.bind(restart_button, "action.restart_bridge")
            restart_button.grid(row=1, column=1, sticky="ew", padx=(5, 0))
            self.action_buttons.append(restart_button)

        # Hide the persistent warning until the first real runtime snapshot says
        # authentication is disabled.
        self._render_auth_banner(True)

    def set_busy(self, busy: bool) -> None:
        """Enable or disable only the actions registered by this view."""
        for button in self.action_buttons:
            button.state(["disabled"] if busy else ["!disabled"])
