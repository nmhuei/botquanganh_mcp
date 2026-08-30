"""Shared visual language for the native BQA Center desktop views."""

from __future__ import annotations

from typing import Any


PALETTE = {
    "app_background": "#10151d",
    "surface": "#18212c",
    "surface_raised": "#1c2735",
    "surface_muted": "#223044",
    "border": "#334155",
    "border_strong": "#475569",
    "text": "#e5edf7",
    "text_muted": "#b6c4d6",
    "text_subtle": "#8ea1b8",
    "accent": "#60a5fa",
    "focus": "#93c5fd",
    "success": "#4ade80",
    "warning": "#fbbf24",
    "danger": "#fb7185",
    "running": "#2dd4bf",
    "tab_background": "#070b0b",
    "tab_green": "#4ade80",
    "tab_green_active": "#a3ff12",
}

# Named Tk fonts inherit the user's desktop text scaling and accessibility
# preferences.  Avoid hard-coded point sizes in the shared theme.
TYPOGRAPHY = {
    "body": "TkDefaultFont",
    "heading": "TkHeadingFont",
    "caption": "TkSmallCaptionFont",
    "mono": "TkFixedFont",
}


def apply_desktop_theme(style: Any, root: Any) -> None:
    """Configure the shared ttk palette before any desktop view is created."""
    try:
        style.theme_use("clam")
    except Exception:
        pass

    root.configure(background=PALETTE["app_background"])

    style.configure("TFrame", background=PALETTE["surface"])
    style.configure(
        "TLabel",
        background=PALETTE["surface"],
        foreground=PALETTE["text"],
        font=TYPOGRAPHY["body"],
    )
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
        foreground=PALETTE["text_muted"],
        font=TYPOGRAPHY["heading"],
    )
    style.configure(
        "TEntry",
        fieldbackground=PALETTE["surface_muted"],
        foreground=PALETTE["text"],
        insertcolor=PALETTE["text"],
        bordercolor=PALETTE["border"],
        lightcolor=PALETTE["border"],
        darkcolor=PALETTE["border"],
        padding=(7, 5),
    )
    style.map(
        "TEntry",
        fieldbackground=[("readonly", PALETTE["surface_muted"])],
        foreground=[("readonly", PALETTE["text"])],
        bordercolor=[("focus", PALETTE["focus"])],
        lightcolor=[("focus", PALETTE["focus"])],
        darkcolor=[("focus", PALETTE["focus"])],
    )
    style.configure(
        "TButton",
        background=PALETTE["surface_muted"],
        foreground=PALETTE["text"],
        bordercolor=PALETTE["border"],
        focuscolor=PALETTE["focus"],
        focusthickness=1,
        padding=(10, 5),
        font=TYPOGRAPHY["body"],
    )
    style.map(
        "TButton",
        background=[
            ("active", PALETTE["border"]),
            ("pressed", PALETTE["accent"]),
            ("disabled", PALETTE["surface"]),
        ],
        foreground=[
            ("pressed", PALETTE["app_background"]),
            ("disabled", PALETTE["text_subtle"]),
        ],
        bordercolor=[("focus", PALETTE["focus"])],
    )

    style.configure("App.TFrame", background=PALETTE["app_background"])
    style.configure("Surface.TFrame", background=PALETTE["surface"])
    style.configure("Raised.TFrame", background=PALETTE["surface_raised"])
    style.configure(
        "Header.TLabel",
        background=PALETTE["app_background"],
        foreground=PALETTE["text"],
        font=TYPOGRAPHY["heading"],
    )
    style.configure(
        "Subtle.TLabel",
        background=PALETTE["app_background"],
        foreground=PALETTE["text_muted"],
        font=TYPOGRAPHY["caption"],
    )
    style.configure(
        "SurfaceSubtle.TLabel",
        background=PALETTE["surface"],
        foreground=PALETTE["text_muted"],
        font=TYPOGRAPHY["caption"],
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
        font=TYPOGRAPHY["heading"],
    )
    style.configure(
        "SectionTitle.TLabel",
        background=PALETTE["surface"],
        foreground=PALETTE["text"],
        font=TYPOGRAPHY["heading"],
    )
    style.configure(
        "Mono.TLabel",
        background=PALETTE["surface"],
        foreground=PALETTE["text"],
        font=TYPOGRAPHY["mono"],
    )
    style.configure(
        "Status.TLabel",
        background=PALETTE["surface_muted"],
        foreground=PALETTE["accent"],
        padding=(10, 5),
        font=TYPOGRAPHY["heading"],
    )
    style.configure("Toolbar.TButton", padding=(10, 5))
    style.configure("Compact.TButton", padding=(8, 4))
    style.configure(
        "Primary.TButton",
        background=PALETTE["accent"],
        foreground=PALETTE["app_background"],
        bordercolor=PALETTE["accent"],
        padding=(12, 6),
    )
    style.map(
        "Primary.TButton",
        background=[
            ("active", PALETTE["focus"]),
            ("pressed", PALETTE["text"]),
            ("disabled", PALETTE["surface_muted"]),
        ],
        foreground=[
            ("active", PALETTE["app_background"]),
            ("pressed", PALETTE["app_background"]),
            ("disabled", PALETTE["text_subtle"]),
        ],
        bordercolor=[("focus", PALETTE["focus"])],
    )

    # A two-option language selector is presented as linked toggle buttons,
    # rather than a dropdown that hides the available choices.
    style.configure(
        "Language.TButton",
        background=PALETTE["surface_muted"],
        foreground=PALETTE["text_muted"],
        bordercolor=PALETTE["border"],
        padding=(9, 4),
    )
    style.configure(
        "LanguageActive.TButton",
        background=PALETTE["tab_green"],
        foreground=PALETTE["app_background"],
        bordercolor=PALETTE["tab_green"],
        padding=(9, 4),
    )
    style.map(
        "LanguageActive.TButton",
        background=[
            ("active", PALETTE["tab_green_active"]),
            ("pressed", PALETTE["tab_green_active"]),
        ],
        foreground=[
            ("active", PALETTE["app_background"]),
            ("pressed", PALETTE["app_background"]),
        ],
        bordercolor=[("focus", PALETTE["focus"])],
    )

    style.configure(
        "Language.TCombobox",
        fieldbackground=PALETTE["surface_muted"],
        background=PALETTE["surface_muted"],
        foreground=PALETTE["text"],
        bordercolor=PALETTE["border"],
        padding=(7, 4),
    )
    style.map(
        "Language.TCombobox",
        fieldbackground=[("readonly", PALETTE["surface_muted"])],
        foreground=[("readonly", PALETTE["text"])],
        bordercolor=[("focus", PALETTE["focus"])],
    )

    style.configure("Chip.TButton", padding=(9, 4))
    style.configure(
        "ChipActive.TButton",
        padding=(9, 4),
        foreground=PALETTE["app_background"],
        background=PALETTE["accent"],
        bordercolor=PALETTE["accent"],
    )
    style.map(
        "ChipActive.TButton",
        background=[
            ("active", PALETTE["focus"]),
            ("pressed", PALETTE["text"]),
        ],
        foreground=[("active", PALETTE["app_background"])],
        bordercolor=[("focus", PALETTE["focus"])],
    )

    style.configure(
        "WarningBanner.TFrame",
        background=PALETTE["surface_muted"],
        borderwidth=1,
        relief="solid",
    )
    style.configure(
        "WarningBanner.TLabel",
        background=PALETTE["surface_muted"],
        foreground=PALETTE["warning"],
        font=TYPOGRAPHY["body"],
    )
    style.configure(
        "Feedback.TLabel",
        background=PALETTE["app_background"],
        foreground=PALETTE["text_muted"],
        font=TYPOGRAPHY["caption"],
    )

    style.configure(
        "App.TNotebook",
        background=PALETTE["tab_background"],
        borderwidth=0,
    )
    style.map(
        "App.TNotebook",
        background=[("selected", PALETTE["tab_background"])],
    )
    style.configure(
        "App.TNotebook.Tab",
        padding=(16, 8),
        background=PALETTE["tab_background"],
        foreground=PALETTE["tab_green"],
        font=TYPOGRAPHY["heading"],
    )
    style.map(
        "App.TNotebook.Tab",
        foreground=[
            ("selected", PALETTE["tab_green_active"]),
            ("active", PALETTE["tab_green_active"]),
        ],
        background=[
            ("selected", PALETTE["tab_background"]),
            ("active", PALETTE["tab_background"]),
        ],
        focuscolor=[("focus", PALETTE["focus"])],
    )

    style.configure(
        "Table.Treeview",
        background=PALETTE["surface"],
        fieldbackground=PALETTE["surface"],
        foreground=PALETTE["text"],
        bordercolor=PALETTE["border"],
        rowheight=30,
        font=TYPOGRAPHY["body"],
    )
    style.map(
        "Table.Treeview",
        background=[("selected", PALETTE["accent"])],
        foreground=[("selected", PALETTE["app_background"])],
        bordercolor=[("focus", PALETTE["focus"])],
    )
    style.configure(
        "Table.Treeview.Heading",
        background=PALETTE["surface_muted"],
        foreground=PALETTE["text_muted"],
        font=TYPOGRAPHY["heading"],
        relief="flat",
        padding=(6, 5),
    )

    style.configure(
        "Inspector.TNotebook",
        background=PALETTE["tab_background"],
        borderwidth=0,
    )
    style.map(
        "Inspector.TNotebook",
        background=[("selected", PALETTE["tab_background"])],
    )
    style.configure(
        "Inspector.TNotebook.Tab",
        padding=(10, 5),
        background=PALETTE["tab_background"],
        foreground=PALETTE["tab_green"],
        font=TYPOGRAPHY["heading"],
    )
    style.map(
        "Inspector.TNotebook.Tab",
        foreground=[
            ("selected", PALETTE["tab_green_active"]),
            ("active", PALETTE["tab_green_active"]),
        ],
        background=[
            ("selected", PALETTE["tab_background"]),
            ("active", PALETTE["tab_background"]),
        ],
        focuscolor=[("focus", PALETTE["focus"])],
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
                highlightthickness=1,
                highlightbackground=PALETTE["border"],
                highlightcolor=PALETTE["focus"],
                background=PALETTE["surface_muted"],
                foreground=PALETTE["text"],
                insertbackground=PALETTE["text"],
                selectbackground=PALETTE["accent"],
                selectforeground=PALETTE["app_background"],
                font=TYPOGRAPHY["mono"],
            )
            yscroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
            xscroll = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
            text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
            text.grid(row=0, column=0, sticky="nsew")
            text.bind(
                "<Control-c>",
                lambda _event, text=text: self.copy_selection(text),
            )
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

    def set_copy_messages(
        self,
        *,
        empty: str,
        success: str,
        selection_success: str,
    ) -> None:
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
