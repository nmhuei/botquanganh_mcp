"""Shared visual language for the native UCS-SecretAgent desktop views."""

from __future__ import annotations

from typing import Any


PALETTE = {
    "app_background": "#10151d",
    "surface": "#18212c",
    "surface_muted": "#223044",
    "border": "#334155",
    "text": "#e5edf7",
    "text_muted": "#b6c4d6",
    "text_subtle": "#8ea1b8",
    "accent": "#60a5fa",
    "success": "#4ade80",
    "warning": "#fbbf24",
    "danger": "#fb7185",
    "running": "#2dd4bf",
    "tab_background": "#070b0b",
    "tab_green": "#4ade80",
    "tab_green_active": "#a3ff12",
}


def apply_desktop_theme(style: Any, root: Any) -> None:
    """Configure the shared ttk palette before any desktop view is created."""
    try:
        style.theme_use("clam")
    except Exception:
        pass
    root.configure(background=PALETTE["app_background"])
    style.configure("TFrame", background=PALETTE["surface"])
    style.configure("TLabel", background=PALETTE["surface"], foreground=PALETTE["text"])
    style.configure(
        "TLabelframe",
        background=PALETTE["surface"],
        foreground=PALETTE["text_muted"],
        bordercolor=PALETTE["border"],
        relief="solid",
    )
    style.configure(
        "TLabelframe.Label",
        background=PALETTE["surface"],
        foreground=PALETTE["text_subtle"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "TEntry",
        fieldbackground=PALETTE["surface_muted"],
        foreground=PALETTE["text"],
        insertcolor=PALETTE["text"],
        bordercolor=PALETTE["border"],
    )
    style.map(
        "TEntry",
        fieldbackground=[("readonly", PALETTE["surface_muted"])],
        foreground=[("readonly", PALETTE["text"])],
    )
    style.configure(
        "TButton",
        background=PALETTE["surface_muted"],
        foreground=PALETTE["text"],
        bordercolor=PALETTE["border"],
        padding=(8, 4),
    )
    style.map(
        "TButton",
        background=[("active", PALETTE["border"]), ("pressed", PALETTE["accent"])],
        foreground=[("pressed", PALETTE["app_background"])],
    )
    style.configure("App.TFrame", background=PALETTE["app_background"])
    style.configure("Surface.TFrame", background=PALETTE["surface"])
    style.configure(
        "Header.TLabel",
        background=PALETTE["app_background"],
        foreground=PALETTE["text"],
        font=("TkDefaultFont", 16, "bold"),
    )
    style.configure(
        "Subtle.TLabel",
        background=PALETTE["app_background"],
        foreground=PALETTE["text_muted"],
    )
    style.configure(
        "Brand.TLabel",
        background=PALETTE["app_background"],
        foreground=PALETTE["text"],
    )
    style.configure(
        "FieldName.TLabel",
        background=PALETTE["surface"],
        foreground=PALETTE["text_subtle"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.configure(
        "Status.TLabel",
        background=PALETTE["surface_muted"],
        foreground=PALETTE["accent"],
        padding=(9, 4),
        font=("TkDefaultFont", 10, "bold"),
    )
    style.configure("Toolbar.TButton", padding=(8, 3))
    style.configure(
        "Language.TCombobox",
        fieldbackground=PALETTE["surface_muted"],
        background=PALETTE["surface_muted"],
        foreground=PALETTE["text"],
        bordercolor=PALETTE["border"],
        padding=(5, 2),
    )
    style.map(
        "Language.TCombobox",
        fieldbackground=[("readonly", PALETTE["surface_muted"])],
        foreground=[("readonly", PALETTE["text"])],
    )
    style.configure("Chip.TButton", padding=(8, 2))
    style.configure(
        "ChipActive.TButton",
        padding=(8, 2),
        foreground=PALETTE["app_background"],
        background=PALETTE["accent"],
    )
    style.map(
        "ChipActive.TButton",
        background=[("active", PALETTE["accent"]), ("pressed", PALETTE["text"])],
        foreground=[("active", PALETTE["app_background"])],
    )
    style.configure("App.TNotebook", background=PALETTE["tab_background"], borderwidth=0)
    style.map("App.TNotebook", background=[("selected", PALETTE["tab_background"])])
    style.configure(
        "App.TNotebook.Tab",
        padding=(14, 7),
        background=PALETTE["tab_background"],
        foreground=PALETTE["tab_green"],
        font=("TkDefaultFont", 10, "bold"),
    )
    style.map(
        "App.TNotebook.Tab",
        foreground=[("selected", PALETTE["tab_green_active"]), ("active", PALETTE["tab_green_active"])],
        background=[("selected", PALETTE["tab_background"]), ("active", PALETTE["tab_background"])],
    )
    style.configure(
        "Table.Treeview",
        background=PALETTE["surface"],
        fieldbackground=PALETTE["surface"],
        foreground=PALETTE["text"],
        bordercolor=PALETTE["border"],
        rowheight=28,
    )
    style.map(
        "Table.Treeview",
        background=[("selected", PALETTE["accent"])],
        foreground=[("selected", PALETTE["app_background"])],
    )
    style.configure(
        "Table.Treeview.Heading",
        background=PALETTE["surface_muted"],
        foreground=PALETTE["text_muted"],
        font=("TkDefaultFont", 9, "bold"),
        relief="flat",
    )
    style.configure("Inspector.TNotebook", background=PALETTE["tab_background"], borderwidth=0)
    style.map("Inspector.TNotebook", background=[("selected", PALETTE["tab_background"])])
    style.configure(
        "Inspector.TNotebook.Tab",
        padding=(9, 4),
        background=PALETTE["tab_background"],
        foreground=PALETTE["tab_green"],
        font=("TkDefaultFont", 9, "bold"),
    )
    style.map(
        "Inspector.TNotebook.Tab",
        foreground=[("selected", PALETTE["tab_green_active"]), ("active", PALETTE["tab_green_active"])],
        background=[("selected", PALETTE["tab_background"]), ("active", PALETTE["tab_background"])],
    )


class InspectorTabs:
    """Reusable read-only inspector whose updates retain a user's scroll position."""

    def __init__(
        self,
        *,
        root: Any,
        tk: Any,
        ttk: Any,
        parent: Any,
        tabs: tuple[tuple[str, str], ...],
        on_message: Any,
        copy_empty_message: str = "No inspector content is available to copy.",
        copy_success_message: str = "Copied the visible inspector content to the clipboard.",
        copy_selection_success_message: str = "Copied selected text to the clipboard.",
    ) -> None:
        self.root = root
        self.on_message = on_message
        self.copy_empty_message = copy_empty_message
        self.copy_success_message = copy_success_message
        self.copy_selection_success_message = copy_selection_success_message
        self.notebook = ttk.Notebook(parent, style="Inspector.TNotebook")
        self.text_by_key: dict[str, Any] = {}
        self.key_by_frame: dict[str, str] = {}
        self.frame_by_key: dict[str, Any] = {}
        for key, label in tabs:
            frame = ttk.Frame(self.notebook, style="Surface.TFrame", padding=6)
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(0, weight=1)
            text = tk.Text(
                frame,
                wrap="none",
                state="disabled",
                borderwidth=0,
                highlightthickness=0,
                background=PALETTE["surface_muted"],
                foreground=PALETTE["text"],
                insertbackground=PALETTE["text"],
                selectbackground=PALETTE["accent"],
                selectforeground=PALETTE["app_background"],
            )
            yscroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
            xscroll = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
            text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
            text.grid(row=0, column=0, sticky="nsew")
            text.bind("<Control-c>", lambda _event, text=text: self.copy_selection(text))
            yscroll.grid(row=0, column=1, sticky="ns")
            xscroll.grid(row=1, column=0, sticky="ew")
            self.notebook.add(frame, text=label)
            self.text_by_key[key] = text
            self.key_by_frame[str(frame)] = key
            self.frame_by_key[key] = frame

    def grid(self, **kwargs: Any) -> None:
        self.notebook.grid(**kwargs)

    def set_content(self, key: str, content: str) -> None:
        """Replace one tab only when content changed, keeping its y-scroll fraction."""
        text = self.text_by_key.get(key)
        if text is None or text.get("1.0", "end-1c") == content:
            return
        try:
            position = float(text.yview()[0])
        except (AttributeError, IndexError, TypeError, ValueError):
            position = None
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("1.0", content)
        text.configure(state="disabled")
        if position is not None:
            text.yview_moveto(position)

    def active_key(self) -> str | None:
        try:
            return self.key_by_frame.get(str(self.notebook.select()))
        except Exception:
            return None

    def set_tab_label(self, key: str, label: str) -> None:
        """Update one tab caption while keeping its existing frame and content."""
        frame = self.frame_by_key.get(key)
        if frame is not None:
            self.notebook.tab(frame, text=label)

    def set_copy_messages(self, *, empty: str, success: str, selection_success: str) -> None:
        """Refresh translatable clipboard feedback without rebuilding the tabs."""
        self.copy_empty_message = empty
        self.copy_success_message = success
        self.copy_selection_success_message = selection_success

    def copy_selection(self, text: Any) -> str:
        """Copy only a highlighted inspector range and suppress full-tab fallback."""
        try:
            selection = text.tag_ranges("sel")
        except Exception:
            return "break"
        if len(selection) != 2:
            return "break"
        content = text.get(selection[0], selection[1])
        if not content:
            return "break"
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.root.update_idletasks()
        self.on_message("success", self.copy_selection_success_message)
        return "break"

    def copy_active(self) -> None:
        key = self.active_key()
        text = self.text_by_key.get(key or "")
        if text is None:
            self.on_message("warn", self.copy_empty_message)
            return
        content = text.get("1.0", "end-1c")
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.root.update_idletasks()
        self.on_message("success", self.copy_success_message)
