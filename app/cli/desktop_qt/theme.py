from __future__ import annotations


THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "canvas": "#090d0c",
        "panel": "#101615",
        "surface": "#121918",
        "surface_2": "#17211f",
        "surface_3": "#1e2926",
        "graphite_deep": "#0c1211",
        "graphite_inset": "#0e1513",
        "graphite_mid": "#151e1b",
        "graphite_raised": "#202b28",
        "panel_raised": "#1b2522",
        "border_subtle": "#202b28",
        "border": "#2a3632",
        "border_strong": "#3a4a44",
        "text": "#f2f5f2",
        "muted": "#a9b5af",
        "subtle": "#81908a",
        "lime": "#a3ff12",
        "success": "#42d5ad",
        "warning": "#f4b942",
        "danger": "#ff6b61",
    },
    "light": {
        "canvas": "#f4f6f8",
        "panel": "#ffffff",
        "surface": "#ffffff",
        "surface_2": "#f1f3f5",
        "surface_3": "#e9ecef",
        "graphite_deep": "#e2e6ea",
        "graphite_inset": "#f8f9fa",
        "graphite_mid": "#edf0f2",
        "graphite_raised": "#dee2e6",
        "panel_raised": "#ffffff",
        "border_subtle": "#e9ecef",
        "border": "#ced4da",
        "border_strong": "#adb5bd",
        "text": "#111827",
        "muted": "#4b5563",
        "subtle": "#6b7280",
        "lime": "#16a34a",
        "success": "#059669",
        "warning": "#d97706",
        "danger": "#dc2626",
    },
    "dracula": {
        "canvas": "#21222c",
        "panel": "#282a36",
        "surface": "#282a36",
        "surface_2": "#343746",
        "surface_3": "#44475a",
        "graphite_deep": "#191a21",
        "graphite_inset": "#21222c",
        "graphite_mid": "#343746",
        "graphite_raised": "#44475a",
        "panel_raised": "#343746",
        "border_subtle": "#343746",
        "border": "#44475a",
        "border_strong": "#6272a4",
        "text": "#f8f8f2",
        "muted": "#949ab5",
        "subtle": "#6272a4",
        "lime": "#bd93f9",
        "success": "#50fa7b",
        "warning": "#f1fa8c",
        "danger": "#ff5555",
    },
    "one_dark": {
        "canvas": "#1e2227",
        "panel": "#21252b",
        "surface": "#282c34",
        "surface_2": "#2c313a",
        "surface_3": "#353b45",
        "graphite_deep": "#1b1d23",
        "graphite_inset": "#21252b",
        "graphite_mid": "#2c313a",
        "graphite_raised": "#3e4451",
        "panel_raised": "#2c313a",
        "border_subtle": "#2c313a",
        "border": "#3e4451",
        "border_strong": "#4b5263",
        "text": "#abb2bf",
        "muted": "#828997",
        "subtle": "#5c6370",
        "lime": "#61afef",
        "success": "#98c379",
        "warning": "#e5c07b",
        "danger": "#e06c75",
    },
    "monokai": {
        "canvas": "#191919",
        "panel": "#222222",
        "surface": "#272822",
        "surface_2": "#2d2a2e",
        "surface_3": "#403e41",
        "graphite_deep": "#141414",
        "graphite_inset": "#1e1e1e",
        "graphite_mid": "#2d2a2e",
        "graphite_raised": "#403e41",
        "panel_raised": "#2d2a2e",
        "border_subtle": "#2d2a2e",
        "border": "#403e41",
        "border_strong": "#5b595c",
        "text": "#fcfcfa",
        "muted": "#939293",
        "subtle": "#727072",
        "lime": "#ffd866",
        "success": "#a9dc76",
        "warning": "#fc9867",
        "danger": "#ff6188",
    },
    "nord": {
        "canvas": "#242933",
        "panel": "#2e3440",
        "surface": "#2e3440",
        "surface_2": "#3b4252",
        "surface_3": "#434c5e",
        "graphite_deep": "#1f232a",
        "graphite_inset": "#2e3440",
        "graphite_mid": "#3b4252",
        "graphite_raised": "#4c566a",
        "panel_raised": "#3b4252",
        "border_subtle": "#3b4252",
        "border": "#434c5e",
        "border_strong": "#4c566a",
        "text": "#eceff4",
        "muted": "#d8dee9",
        "subtle": "#616e88",
        "lime": "#88c0d0",
        "success": "#a3be8c",
        "warning": "#ebcb8b",
        "danger": "#bf616a",
    },
    "tokyo_night": {
        "canvas": "#16161e",
        "panel": "#1a1b26",
        "surface": "#1a1b26",
        "surface_2": "#24283b",
        "surface_3": "#2f354f",
        "graphite_deep": "#13141c",
        "graphite_inset": "#1a1b26",
        "graphite_mid": "#24283b",
        "graphite_raised": "#3b4261",
        "panel_raised": "#24283b",
        "border_subtle": "#24283b",
        "border": "#2f354f",
        "border_strong": "#414868",
        "text": "#c0caf5",
        "muted": "#9aa5ce",
        "subtle": "#565f89",
        "lime": "#7dcfff",
        "success": "#9ece6a",
        "warning": "#e0af68",
        "danger": "#f7768e",
    },
    "gruvbox": {
        "canvas": "#1d2021",
        "panel": "#282828",
        "surface": "#282828",
        "surface_2": "#32302f",
        "surface_3": "#3c3836",
        "graphite_deep": "#18191a",
        "graphite_inset": "#282828",
        "graphite_mid": "#32302f",
        "graphite_raised": "#504945",
        "panel_raised": "#32302f",
        "border_subtle": "#32302f",
        "border": "#3c3836",
        "border_strong": "#504945",
        "text": "#ebdbb2",
        "muted": "#a89984",
        "subtle": "#7c6f64",
        "lime": "#fabd2f",
        "success": "#b8bb26",
        "warning": "#fe8019",
        "danger": "#fb4934",
    },
    "catppuccin": {
        "canvas": "#11111b",
        "panel": "#181825",
        "surface": "#1e1e2e",
        "surface_2": "#313244",
        "surface_3": "#45475a",
        "graphite_deep": "#0f0f17",
        "graphite_inset": "#181825",
        "graphite_mid": "#313244",
        "graphite_raised": "#45475a",
        "panel_raised": "#313244",
        "border_subtle": "#313244",
        "border": "#45475a",
        "border_strong": "#585b70",
        "text": "#cdd6f4",
        "muted": "#a6adc8",
        "subtle": "#6c7086",
        "lime": "#cba6f7",
        "success": "#a6e3a1",
        "warning": "#f9e2af",
        "danger": "#f38ba8",
    },
    "synthwave": {
        "canvas": "#1a1528",
        "panel": "#241b2f",
        "surface": "#262335",
        "surface_2": "#34294f",
        "surface_3": "#463465",
        "graphite_deep": "#140f20",
        "graphite_inset": "#241b2f",
        "graphite_mid": "#34294f",
        "graphite_raised": "#463465",
        "panel_raised": "#34294f",
        "border_subtle": "#34294f",
        "border": "#463465",
        "border_strong": "#614d85",
        "text": "#f92aad",
        "muted": "#b48ead",
        "subtle": "#715b8a",
        "lime": "#ff7edb",
        "success": "#36f9f6",
        "warning": "#fede5d",
        "danger": "#fe4450",
    },
    "solarized_dark": {
        "canvas": "#00212b",
        "panel": "#002b36",
        "surface": "#073642",
        "surface_2": "#094352",
        "surface_3": "#0e5264",
        "graphite_deep": "#001820",
        "graphite_inset": "#002b36",
        "graphite_mid": "#073642",
        "graphite_raised": "#0e5264",
        "panel_raised": "#073642",
        "border_subtle": "#073642",
        "border": "#0e5264",
        "border_strong": "#1a6478",
        "text": "#839496",
        "muted": "#93a1a1",
        "subtle": "#586e75",
        "lime": "#2aa198",
        "success": "#859900",
        "warning": "#b58900",
        "danger": "#dc322f",
    },
    "github_dark": {
        "canvas": "#1c2128",
        "panel": "#22272e",
        "surface": "#22272e",
        "surface_2": "#2d333b",
        "surface_3": "#373e47",
        "graphite_deep": "#171b21",
        "graphite_inset": "#22272e",
        "graphite_mid": "#2d333b",
        "graphite_raised": "#444c56",
        "panel_raised": "#2d333b",
        "border_subtle": "#2d333b",
        "border": "#373e47",
        "border_strong": "#545d68",
        "text": "#adbac7",
        "muted": "#768390",
        "subtle": "#545d68",
        "lime": "#539bf5",
        "success": "#57ab5a",
        "warning": "#c69026",
        "danger": "#e5534b",
    },
}

DARK_COLORS = THEMES["dark"]
LIGHT_COLORS = THEMES["light"]
COLORS = DARK_COLORS

THEME_LIST: list[dict[str, Any]] = [
    {
        "id": "dark",
        "icon": "🌙",
        "preview": ["#090d0c", "#101615", "#a3ff12", "#f2f5f2"],
    },
    {
        "id": "light",
        "icon": "☀️",
        "preview": ["#f4f6f8", "#ffffff", "#16a34a", "#111827"],
    },
    {
        "id": "dracula",
        "icon": "🧛",
        "preview": ["#21222c", "#282a36", "#bd93f9", "#f8f8f2"],
    },
    {
        "id": "one_dark",
        "icon": "🎨",
        "preview": ["#1e2227", "#21252b", "#61afef", "#abb2bf"],
    },
    {
        "id": "monokai",
        "icon": "✨",
        "preview": ["#191919", "#272822", "#ffd866", "#fcfcfa"],
    },
    {
        "id": "nord",
        "icon": "❄️",
        "preview": ["#242933", "#2e3440", "#88c0d0", "#eceff4"],
    },
    {
        "id": "tokyo_night",
        "icon": "🌆",
        "preview": ["#16161e", "#1a1b26", "#7dcfff", "#c0caf5"],
    },
    {
        "id": "gruvbox",
        "icon": "🪵",
        "preview": ["#1d2021", "#282828", "#fabd2f", "#ebdbb2"],
    },
    {
        "id": "catppuccin",
        "icon": "☕",
        "preview": ["#11111b", "#1e1e2e", "#cba6f7", "#cdd6f4"],
    },
    {
        "id": "synthwave",
        "icon": "📼",
        "preview": ["#1a1528", "#262335", "#ff7edb", "#f92aad"],
    },
    {
        "id": "solarized_dark",
        "icon": "🌊",
        "preview": ["#00212b", "#002b36", "#2aa198", "#839496"],
    },
    {
        "id": "github_dark",
        "icon": "🐙",
        "preview": ["#1c2128", "#22272e", "#539bf5", "#adbac7"],
    },
]


def list_available_themes() -> list[dict[str, Any]]:
    return list(THEME_LIST)


def get_theme_colors(theme: str = "dark") -> dict[str, str]:
    normalized = str(theme).strip().lower()
    if normalized in THEMES:
        return THEMES[normalized]
    if "light" in normalized:
        return THEMES["light"]
    return THEMES["dark"]

LAYOUT = {
    "header_height": 64,
    "rail_width": 76,
    "space_xs": 4,
    "space_sm": 8,
    "space_md": 12,
    "space_lg": 16,
    "radius_sm": 6,
    "radius_md": 8,
    "font_meta": 11,
    "font_body": 14,
    "font_title": 16,
}


def build_stylesheet(theme: str = "dark") -> str:
    colors = get_theme_colors(theme)
    return f"""
    QMainWindow, QWidget#appRoot {{
        background: {colors["canvas"]};
        color: {colors["text"]};
        font-size: 13px;
    }}
    QWidget#runtimePage, QWidget#workspaceLogsPage, QWidget#activityPage, QWidget#aboutPage, QWidget#settingsPage {{
        background: {colors["canvas"]};
        color: {colors["text"]};
    }}
    QLabel {{
        color: {colors["text"]};
        background: transparent;
    }}
    QFrame#commandHeader {{
        background: {colors["panel"]};
        border: 0;
        border-bottom: 1px solid {colors["border"]};
    }}
    QFrame#commandBrand {{
        background: transparent;
        border: 0;
    }}
    QLabel[role="brandName"] {{
        color: {colors["text"]};
        font-size: 20px;
        font-weight: 700;
    }}
    QLabel[role="brandIdentity"], QLabel[role="sectionEyebrow"] {{
        color: {colors["lime"]};
        font-size: {LAYOUT["font_meta"]}px;
        font-weight: 700;
    }}
    QLabel[role="headerSubtitle"], QLabel[role="pageSubtitle"] {{
        color: {colors["muted"]};
        font-size: 12px;
    }}
    QLabel[role="pageTitle"] {{
        color: {colors["text"]};
        font-size: 24px;
        font-weight: 700;
    }}
    QLabel[role="sectionTitle"], QLabel[role="cardTitle"] {{
        color: {colors["text"]};
        font-size: 14px;
        font-weight: 700;
    }}
    QFrame#iconRail {{
        background: {colors["panel"]};
        border: 0;
        border-right: 1px solid {colors["border"]};
    }}
    QFrame#contentCanvas {{
        background: {colors["canvas"]};
        border: 0;
    }}
    QFrame#footerBar {{
        background: {colors["panel"]};
        border: 0;
        border-top: 1px solid {colors["border"]};
    }}
    QFrame#footerSeparator {{
        color: {colors["border_strong"]};
        max-width: 1px;
    }}
    QPushButton#iconRailItem {{
        min-width: 0;
        min-height: 0;
        padding: 4px;
        background: transparent;
        color: {colors["muted"]};
        border: 2px solid transparent;
        border-left-width: 3px;
        border-right-width: 3px;
        border-radius: 0;
    }}
    QPushButton#iconRailItem[active="true"] {{
        background: {colors["graphite_mid"]};
        color: {colors["lime"]};
        border-left-color: {colors["lime"]};
    }}
    QPushButton#iconRailItem:focus {{
        border-color: {colors["lime"]};
        border-left-width: 3px;
        border-right-width: 3px;
    }}
    QWidget[role="card"] {{
        background: {colors["panel"]};
        border: 1px solid {colors["border"]};
        border-radius: 8px;
    }}
    QFrame#panelFrame {{
        background: {colors["panel"]};
        border: 1px solid {colors["border"]};
        border-radius: {LAYOUT["radius_md"]}px;
    }}
    QPushButton {{
        background: {colors["surface_2"]};
        color: {colors["text"]};
        border: 1px solid {colors["border"]};
        border-radius: 8px;
        padding: 5px 12px;
        font-size: 11px;
    }}
    QFrame#runtimeActionDock QPushButton, QFrame#runtimeWorkspaceFrame QPushButton {{
        padding: 4px 8px;
        min-height: 28px;
        font-size: 11px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        border-color: {colors["lime"]};
    }}
    QPushButton[variant="primary"] {{
        color: {colors["canvas"]};
        background: {colors["lime"]};
        border-color: {colors["lime"]};
    }}
    QPushButton[variant="danger"] {{
        color: {colors["canvas"]};
        background: {colors["danger"]};
        border-color: {colors["danger"]};
    }}
    QPushButton[variant="neutral"], QPushButton[variant="secondary"] {{
        background: {colors["surface_2"]};
        color: {colors["text"]};
    }}
    QPushButton[role="compactAction"] {{
        min-height: 28px;
        padding: 4px 8px;
        border-radius: {LAYOUT["radius_sm"]}px;
    }}
    QPushButton:disabled {{
        color: {colors["subtle"]};
        background: {colors["surface"]};
        border-color: {colors["border"]};
    }}
    QTableView {{
        background: {colors["surface"]};
        alternate-background-color: {colors["surface_2"]};
        color: {colors["text"]};
        gridline-color: {colors["border"]};
        selection-background-color: {colors["surface_3"]};
        selection-color: {colors["lime"]};
        border: 1px solid {colors["border"]};
    }}
    QHeaderView {{
        background: {colors["surface"]};
        color: {colors["muted"]};
    }}
    QHeaderView::section, QTableCornerButton::section {{
        background: {colors["surface_2"]};
        color: {colors["muted"]};
        border: 0;
        border-bottom: 1px solid {colors["border"]};
        padding: 6px 8px;
        font-size: 11px;
        font-weight: 700;
    }}
    QTableView::item {{
        padding: 6px 8px;
        border-bottom: 1px solid {colors["border_subtle"]};
    }}
    QTableView::item:hover:!selected {{
        background: {colors["graphite_mid"]};
    }}
    QTableView::item:selected {{
        background: {colors["graphite_raised"]};
        color: {colors["lime"]};
    }}
    QPushButton#headerCopyEndpointButton {{
        background: {colors["graphite_inset"]};
        color: {colors["lime"]};
        border: 1px solid {colors["border"]};
        font-weight: 600;
    }}
    QPushButton#headerCopyEndpointButton:hover {{
        border-color: {colors["lime"]};
        background: {colors["graphite_raised"]};
    }}
    QLabel#activityCommandStatsBar {{
        color: {colors["muted"]};
        font-size: 11px;
        font-family: "JetBrains Mono", "Cascadia Code", "Fira Code", monospace;
        padding-bottom: 2px;
    }}
    QLabel#activityInspectorTelemetry {{
        color: {colors["subtle"]};
        font-size: 10px;
        font-family: "JetBrains Mono", "Cascadia Code", "Fira Code", monospace;
        padding: 4px 6px;
    }}
    QLineEdit, QComboBox, QSpinBox {{
        min-height: 28px;
        background: {colors["graphite_inset"]};
        color: {colors["text"]};
        border: 1px solid {colors["border"]};
        border-radius: {LAYOUT["radius_sm"]}px;
        padding: 3px 7px;
    }}
    QSpinBox::up-button, QSpinBox::down-button {{
        background: {colors["graphite_mid"]};
        border: 0;
        width: 18px;
    }}
    QCheckBox {{
        color: {colors["text"]};
        spacing: 8px;
        font-size: {LAYOUT["font_body"]}px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {colors["border"]};
        border-radius: 3px;
        background: {colors["graphite_inset"]};
    }}
    QCheckBox::indicator:checked {{
        background: {colors["lime"]};
        border-color: {colors["lime"]};
    }}
    QComboBox::drop-down {{
        background: {colors["graphite_mid"]};
        border: 0;
        border-left: 1px solid {colors["border"]};
        width: 22px;
    }}
    QComboBox QAbstractItemView {{
        background: {colors["graphite_inset"]};
        color: {colors["text"]};
        border: 1px solid {colors["border_strong"]};
        selection-background-color: {colors["graphite_raised"]};
        selection-color: {colors["lime"]};
        outline: 0;
    }}
    QTabWidget {{
        background: {colors["graphite_deep"]};
    }}
    QTabWidget::pane {{
        background: {colors["graphite_inset"]};
        border: 1px solid {colors["border"]};
        border-radius: {LAYOUT["radius_sm"]}px;
        top: -1px;
    }}
    QTabBar {{
        background: {colors["graphite_deep"]};
    }}
    QTabBar::tab {{
        background: {colors["graphite_deep"]};
        color: {colors["muted"]};
        border: 1px solid {colors["border"]};
        border-bottom: 0;
        border-top-left-radius: {LAYOUT["radius_sm"]}px;
        border-top-right-radius: {LAYOUT["radius_sm"]}px;
        padding: 6px 10px;
        margin-right: 2px;
    }}
    QTabBar::tab:hover {{
        background: {colors["graphite_mid"]};
        color: {colors["text"]};
        border-color: {colors["border_strong"]};
    }}
    QTabBar::tab:selected {{
        background: {colors["graphite_inset"]};
        color: {colors["lime"]};
        border-color: {colors["lime"]};
    }}
    QTabBar QToolButton {{
        background: {colors["graphite_mid"]};
        color: {colors["text"]};
        border: 1px solid {colors["border"]};
        border-radius: 3px;
    }}
    QTabBar QToolButton:hover {{
        background: {colors["graphite_raised"]};
        color: {colors["lime"]};
    }}
    QTextEdit, QTextBrowser, QPlainTextEdit {{
        background: {colors["graphite_inset"]};
        color: {colors["text"]};
        border: 0;
        selection-background-color: {colors["graphite_raised"]};
        selection-color: {colors["lime"]};
    }}
    QPlainTextEdit#activityCommandInput,
    QPlainTextEdit[objectName^="activityInspector"] {{
        background: {colors["graphite_inset"]};
        color: {colors["text"]};
        font-family: "JetBrains Mono", "Cascadia Code", "Fira Code", "Consolas", "Monaco", "DejaVu Sans Mono", monospace;
        font-size: 13px;
        padding: 10px;
    }}
    QTextEdit::viewport, QTextBrowser::viewport, QPlainTextEdit::viewport {{
        background: {colors["graphite_inset"]};
    }}
    QScrollBar:vertical {{
        background: {colors["graphite_deep"]};
        width: 10px;
        margin: 0;
    }}
    QScrollBar:horizontal {{
        background: {colors["graphite_deep"]};
        height: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
        background: {colors["border_strong"]};
        border: 2px solid {colors["graphite_deep"]};
        border-radius: 4px;
        min-height: 24px;
        min-width: 24px;
    }}
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
        background: {colors["muted"]};
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        background: {colors["graphite_deep"]};
        border: 0;
    }}
    QScrollBar::add-page, QScrollBar::sub-page {{
        background: {colors["graphite_deep"]};
    }}
    QAbstractScrollArea::corner {{
        background: {colors["graphite_deep"]};
        border: 0;
    }}
    QSplitter::handle {{
        background: {colors["graphite_deep"]};
    }}
    QSplitter::handle:hover {{
        background: {colors["border_strong"]};
    }}
    QToolTip {{
        background: {colors["graphite_raised"]};
        color: {colors["text"]};
        border: 1px solid {colors["lime"]};
        padding: 4px;
    }}
    QWidget:disabled, QAbstractItemView:disabled {{
        color: {colors["subtle"]};
        background: {colors["graphite_deep"]};
        border-color: {colors["border_subtle"]};
    }}
    QFrame#metricStrip, QFrame#runtimeMetricStrip {{
        background: {colors["graphite_deep"]};
        border: 1px solid {colors["border"]};
        border-radius: {LAYOUT["radius_md"]}px;
    }}
    QFrame#metricCell {{
        background: {colors["graphite_mid"]};
        border: 1px solid {colors["border_subtle"]};
        border-radius: {LAYOUT["radius_sm"]}px;
    }}
    QFrame#serviceDetailCard {{
        background: {colors["surface"]};
        border: 1px solid {colors["border"]};
        border-radius: {LAYOUT["radius_md"]}px;
    }}
    QFrame#serviceDetailCard QLabel[role="sectionTitle"] {{
        font-size: 12px;
        font-weight: 700;
    }}
    QFrame#detailRow {{
        background: {colors["graphite_inset"]};
        border: 0;
        border-bottom: 1px solid {colors["border_subtle"]};
        border-radius: 0;
        min-height: 24px;
    }}
    QFrame#denseToolbar, QFrame#actionDock, QFrame#runtimeActionDock,
    QFrame#runtimeWorkspaceFrame, QFrame#activityCommandToolbar,
    QFrame#activityInvestigationControls, QFrame#runtimeLiveClock,
    QFrame#runtimeTopologyDiagram {{
        background: {colors["graphite_mid"]};
        border: 1px solid {colors["border"]};
        border-radius: {LAYOUT["radius_md"]}px;
    }}
    QFrame#runtimeActionDock {{
        background: {colors["panel_raised"]};
        border-color: {colors["border_strong"]};
    }}
    QFrame#pageHeader {{
        background: transparent;
        border: 0;
    }}
    QFrame#workspaceInspectorDetailGrid {{
        background: {colors["graphite_mid"]};
        border: 1px solid {colors["border_subtle"]};
        border-radius: {LAYOUT["radius_sm"]}px;
    }}
    QLabel[role="inspectorValue"] {{
        color: {colors["lime"]};
        font-weight: 700;
    }}
    QFrame#inspectorSurface, QFrame#workspaceLogsInspectorFrame,
    QFrame#activityInputSurface, QFrame#emptySurface {{
        background: {colors["graphite_inset"]};
        border: 1px solid {colors["border"]};
        border-radius: {LAYOUT["radius_md"]}px;
    }}
    QLabel[role="metricLabel"], QLabel[role="detailLabel"] {{
        color: {colors["muted"]};
        font-size: {LAYOUT["font_meta"]}px;
        padding: 0px 0px 1px 0px;
    }}
    QLabel[role="metricValue"], QLabel[role="detailValue"] {{
        color: {colors["text"]};
        font-weight: 700;
        padding: 0px 0px 1px 0px;
    }}
    QLabel[role="pill"] {{
        color: {colors["text"]};
        background: {colors["surface_3"]};
        border: 1px solid {colors["border"]};
        border-radius: 10px;
    }}
    QLabel[role="pill"][state="loading"] {{
        color: {colors["muted"]};
    }}
    QLabel[role="pill"][state="error"] {{
        color: {colors["danger"]};
        border-color: {colors["danger"]};
    }}
    QLabel[role="pill"][state="ready"], QLabel[role="pill"][state="success"] {{
        color: {colors["success"]};
        border-color: {colors["success"]};
    }}
    QLabel[role="pill"][state="warning"], QLabel[role="pill"][state="warn"] {{
        color: {colors["warning"]};
        border-color: {colors["warning"]};
    }}
    QLabel[role="pill"][state="stopped"] {{
        color: {colors["subtle"]};
        border-color: {colors["border_strong"]};
    }}
    QLabel[role="footerStatus"] {{
        color: {colors["muted"]};
        font-size: {LAYOUT["font_meta"]}px;
    }}
    QPushButton:focus, QLineEdit:focus, QComboBox:focus, QTableView:focus,
    QTextEdit:focus, QTextBrowser:focus, QPlainTextEdit:focus, QTabBar::tab:focus {{
        border: 2px solid {colors["lime"]};
    }}
    """
