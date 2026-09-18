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
        self.summary_var = tk.StringVar(value="")
        self.backend_var = tk.StringVar(value="backend: …")
        self.message_var = tk.StringVar(value=initial_message)
        self.action_buttons: list[Any] = []
        self.latest_data: dict[str, Any] | None = None

    def render(self, data: dict[str, Any]) -> RuntimePresentation:
        """Apply a status response and return its normalized presentation."""
        self.latest_data = dict(data)
        presentation = runtime_presentation(data, self.translator)
        self.status_var.set(presentation.status)
        self.summary_var.set(presentation.summary)
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
        on_start: Any = None,
        on_stop: Any = None,
        on_restart: Any = None,
        on_refresh: Any = None,
    ) -> None:
        """Compose factual runtime controls without reaching into the dashboard."""
        on_start = on_start or (lambda: None)
        on_stop = on_stop or (lambda: None)
        on_restart = on_restart or (lambda: None)
        on_refresh = on_refresh or (lambda: None)
        self.action_buttons = []

        surface = ttk.Frame(parent, style="Surface.TFrame")
        surface.pack(fill="both", expand=True)

        health = ttk.Frame(surface, style="Surface.TFrame")
        health.pack(fill="x", pady=(0, 14))
        status_label = ttk.Label(health, textvariable=self.status_var, style="Status.TLabel")
        status_label.pack(side="left")
        ttk.Label(
            health,
            textvariable=self.summary_var,
            style="SurfaceSubtle.TLabel",
            wraplength=620,
        ).pack(side="left", padx=(12, 0))

        cards = ttk.Frame(surface, style="Surface.TFrame")
        cards.pack(fill="x", pady=(0, 14))
        for column in range(3):
            cards.columnconfigure(column, weight=1)
        card_specs = (
            ("field.mcp_bridge", "bridge", "field.authentication", "authentication"),
            ("field.server", "server", "field.endpoint", "endpoint"),
            ("field.tunnel", "tunnel", "field.endpoint", "endpoint"),
        )
        for column, (title_key, state_key, detail_key, detail_value_key) in enumerate(card_specs):
            self._service_card(
                ttk,
                cards,
                title_key=title_key,
                state_var=self.values[state_key],
                detail_key=detail_key,
                detail_var=self.values[detail_value_key],
            ).grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=(0, 10) if column < 2 else 0,
            )

        controls = ttk.Frame(surface, style="Surface.TFrame")
        controls.pack(fill="x", pady=(0, 14))
        controls_label = ttk.Label(controls, style="FieldName.TLabel")
        self.bindings.bind(controls_label, "runtime.controls")
        controls_label.pack(side="left", padx=(0, 12))
        for key, callback, style in (
            ("action.start", on_start, "Primary.TButton"),
            ("action.stop", on_stop, "Danger.TButton"),
            ("action.restart", on_restart, "Secondary.TButton"),
            ("action.refresh", on_refresh, "Secondary.TButton"),
        ):
            button = ttk.Button(controls, style=style, command=callback)
            self.bindings.bind(button, key)
            button.pack(side="left", padx=(0, 8))
            self.action_buttons.append(button)

        endpoint = ttk.Frame(surface, style="Surface.TFrame")
        endpoint.pack(fill="x", pady=(0, 10))
        endpoint_label = ttk.Label(endpoint, style="FieldName.TLabel")
        self.bindings.bind(endpoint_label, "field.endpoint")
        endpoint_label.grid(row=0, column=0, sticky="w", padx=(0, 12))
        endpoint.columnconfigure(1, weight=1)
        ttk.Label(
            endpoint,
            textvariable=self.values["endpoint"],
            style="CardValue.TLabel",
            wraplength=520,
        ).grid(row=0, column=1, sticky="w")
        copy_button = ttk.Button(endpoint, style="Secondary.TButton", command=on_copy_endpoint)
        self.bindings.bind(copy_button, "action.copy")
        copy_button.grid(row=0, column=2, sticky="e", padx=(12, 0))

        workspace = ttk.Frame(surface, style="Surface.TFrame")
        workspace.pack(fill="x")
        workspace_label = ttk.Label(workspace, style="FieldName.TLabel")
        self.bindings.bind(workspace_label, "field.workspace")
        workspace_label.grid(row=0, column=0, sticky="w", padx=(0, 12))
        workspace.columnconfigure(1, weight=1)
        ttk.Entry(workspace, textvariable=workspace_var, state="readonly", width=58).grid(
            row=0, column=1, sticky="ew"
        )
        choose_button = ttk.Button(
            workspace, style="Secondary.TButton", command=on_choose_workspace
        )
        self.bindings.bind(choose_button, "action.choose_folder")
        choose_button.grid(row=0, column=2, sticky="e", padx=(12, 0))
        apply_button = ttk.Button(
            workspace, style="Primary.TButton", command=on_apply_workspace
        )
        self.bindings.bind(apply_button, "action.apply")
        apply_button.grid(row=0, column=3, sticky="e", padx=(8, 0))
        self.action_buttons.append(apply_button)

    def _service_card(
        self,
        ttk: Any,
        parent: Any,
        *,
        title_key: str,
        state_var: Any,
        detail_key: str,
        detail_var: Any,
    ) -> Any:
        """Build one factual service card bound to RuntimeView variables."""
        card = ttk.LabelFrame(parent, style="RuntimeCard.TLabelframe", padding=16)
        self.bindings.bind(card, title_key)
        ttk.Label(card, textvariable=state_var, style="RuntimeState.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        detail = ttk.Label(card, style="FieldName.TLabel")
        self.bindings.bind(detail, detail_key)
        detail.grid(row=1, column=0, sticky="w", pady=(12, 2))
        ttk.Label(card, textvariable=detail_var, style="CardValue.TLabel", wraplength=220).grid(
            row=2, column=0, sticky="w"
        )
        return card

    def set_busy(self, busy: bool) -> None:
        """Enable or disable only the actions registered by this view."""
        for button in self.action_buttons:
            button.state(["disabled"] if busy else ["!disabled"])
