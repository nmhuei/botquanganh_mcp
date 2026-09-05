from __future__ import annotations


COLORS = {
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
}

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


def build_stylesheet() -> str:
    return f"""
    QMainWindow, QWidget#appRoot {{
        background: {COLORS["canvas"]};
        color: {COLORS["text"]};
        font-size: 13px;
    }}
    QWidget#runtimePage, QWidget#workspaceLogsPage, QWidget#activityPage {{
        background: {COLORS["canvas"]};
        color: {COLORS["text"]};
    }}
    QLabel {{
        color: {COLORS["text"]};
        background: transparent;
    }}
    QFrame#commandHeader {{
        background: {COLORS["panel"]};
        border: 0;
        border-bottom: 1px solid {COLORS["border"]};
    }}
    QFrame#commandBrand {{
        background: transparent;
        border: 0;
    }}
    QLabel[role="brandName"] {{
        color: {COLORS["text"]};
        font-size: 20px;
        font-weight: 700;
    }}
    QLabel[role="brandIdentity"], QLabel[role="sectionEyebrow"] {{
        color: {COLORS["lime"]};
        font-size: {LAYOUT["font_meta"]}px;
        font-weight: 700;
    }}
    QLabel[role="headerSubtitle"], QLabel[role="pageSubtitle"] {{
        color: {COLORS["muted"]};
        font-size: 12px;
    }}
    QLabel[role="pageTitle"] {{
        color: {COLORS["text"]};
        font-size: 24px;
        font-weight: 700;
    }}
    QLabel[role="sectionTitle"], QLabel[role="cardTitle"] {{
        color: {COLORS["text"]};
        font-size: 14px;
        font-weight: 700;
    }}
    QFrame#iconRail {{
        background: {COLORS["panel"]};
        border: 0;
        border-right: 1px solid {COLORS["border"]};
    }}
    QFrame#contentCanvas {{
        background: {COLORS["canvas"]};
        border: 0;
    }}
    QFrame#footerBar {{
        background: {COLORS["panel"]};
        border: 0;
        border-top: 1px solid {COLORS["border"]};
    }}
    QFrame#footerSeparator {{
        color: {COLORS["border_strong"]};
        max-width: 1px;
    }}
    QPushButton#iconRailItem {{
        min-width: 0;
        min-height: 0;
        padding: 4px;
        background: transparent;
        color: {COLORS["muted"]};
        border: 2px solid transparent;
        border-left-width: 3px;
        border-right-width: 3px;
        border-radius: 0;
    }}
    QPushButton#iconRailItem[active="true"] {{
        background: {COLORS["graphite_mid"]};
        color: {COLORS["lime"]};
        border-left-color: {COLORS["lime"]};
    }}
    QPushButton#iconRailItem:focus {{
        border-color: {COLORS["lime"]};
        border-left-width: 3px;
        border-right-width: 3px;
    }}
    QWidget[role="card"] {{
        background: {COLORS["panel"]};
        border: 1px solid {COLORS["border"]};
        border-radius: 8px;
    }}
    QFrame#panelFrame {{
        background: {COLORS["panel"]};
        border: 1px solid {COLORS["border"]};
        border-radius: {LAYOUT["radius_md"]}px;
    }}
    QPushButton {{
        background: {COLORS["surface_2"]};
        color: {COLORS["text"]};
        border: 1px solid {COLORS["border"]};
        border-radius: 8px;
        padding: 10px 14px;
    }}
    QPushButton:hover {{
        border-color: {COLORS["lime"]};
    }}
    QPushButton[variant="primary"] {{
        color: {COLORS["canvas"]};
        background: {COLORS["lime"]};
        border-color: {COLORS["lime"]};
    }}
    QPushButton[variant="danger"] {{
        color: {COLORS["canvas"]};
        background: {COLORS["danger"]};
        border-color: {COLORS["danger"]};
    }}
    QPushButton[variant="neutral"], QPushButton[variant="secondary"] {{
        background: {COLORS["surface_2"]};
        color: {COLORS["text"]};
    }}
    QPushButton[role="compactAction"] {{
        min-height: 28px;
        padding: 4px 8px;
        border-radius: {LAYOUT["radius_sm"]}px;
    }}
    QPushButton:disabled {{
        color: {COLORS["subtle"]};
        background: {COLORS["surface"]};
        border-color: {COLORS["border"]};
    }}
    QTableView {{
        background: {COLORS["surface"]};
        alternate-background-color: {COLORS["surface_2"]};
        color: {COLORS["text"]};
        gridline-color: {COLORS["border"]};
        selection-background-color: {COLORS["surface_3"]};
        selection-color: {COLORS["lime"]};
        border: 1px solid {COLORS["border"]};
    }}
    QHeaderView {{
        background: {COLORS["surface"]};
        color: {COLORS["muted"]};
    }}
    QHeaderView::section, QTableCornerButton::section {{
        background: {COLORS["surface_2"]};
        color: {COLORS["muted"]};
        border: 0;
        border-bottom: 1px solid {COLORS["border"]};
        padding: 6px 8px;
        font-size: 11px;
        font-weight: 700;
    }}
    QTableView::item {{
        padding: 6px 8px;
        border-bottom: 1px solid {COLORS["border_subtle"]};
    }}
    QTableView::item:selected {{
        background: {COLORS["graphite_raised"]};
        color: {COLORS["lime"]};
    }}
    QLineEdit, QComboBox {{
        min-height: 28px;
        background: {COLORS["graphite_inset"]};
        color: {COLORS["text"]};
        border: 1px solid {COLORS["border"]};
        border-radius: {LAYOUT["radius_sm"]}px;
        padding: 3px 7px;
    }}
    QComboBox::drop-down {{
        background: {COLORS["graphite_mid"]};
        border: 0;
        border-left: 1px solid {COLORS["border"]};
        width: 22px;
    }}
    QComboBox QAbstractItemView {{
        background: {COLORS["graphite_inset"]};
        color: {COLORS["text"]};
        border: 1px solid {COLORS["border_strong"]};
        selection-background-color: {COLORS["graphite_raised"]};
        selection-color: {COLORS["lime"]};
        outline: 0;
    }}
    QTabWidget {{
        background: {COLORS["graphite_deep"]};
    }}
    QTabWidget::pane {{
        background: {COLORS["graphite_inset"]};
        border: 1px solid {COLORS["border"]};
        border-radius: {LAYOUT["radius_sm"]}px;
        top: -1px;
    }}
    QTabBar {{
        background: {COLORS["graphite_deep"]};
    }}
    QTabBar::tab {{
        background: {COLORS["graphite_deep"]};
        color: {COLORS["muted"]};
        border: 1px solid {COLORS["border"]};
        border-bottom: 0;
        border-top-left-radius: {LAYOUT["radius_sm"]}px;
        border-top-right-radius: {LAYOUT["radius_sm"]}px;
        padding: 6px 10px;
        margin-right: 2px;
    }}
    QTabBar::tab:hover {{
        background: {COLORS["graphite_mid"]};
        color: {COLORS["text"]};
        border-color: {COLORS["border_strong"]};
    }}
    QTabBar::tab:selected {{
        background: {COLORS["graphite_inset"]};
        color: {COLORS["lime"]};
        border-color: {COLORS["lime"]};
    }}
    QTextEdit, QTextBrowser, QPlainTextEdit {{
        background: {COLORS["graphite_inset"]};
        color: {COLORS["text"]};
        border: 0;
        selection-background-color: {COLORS["graphite_raised"]};
        selection-color: {COLORS["lime"]};
    }}
    QTextEdit::viewport, QTextBrowser::viewport, QPlainTextEdit::viewport {{
        background: {COLORS["graphite_inset"]};
    }}
    QScrollBar:vertical {{
        background: {COLORS["graphite_deep"]};
        width: 10px;
        margin: 0;
    }}
    QScrollBar:horizontal {{
        background: {COLORS["graphite_deep"]};
        height: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
        background: {COLORS["border_strong"]};
        border: 2px solid {COLORS["graphite_deep"]};
        border-radius: 4px;
        min-height: 24px;
        min-width: 24px;
    }}
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
        background: {COLORS["muted"]};
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        background: {COLORS["graphite_deep"]};
        border: 0;
    }}
    QScrollBar::add-page, QScrollBar::sub-page {{
        background: {COLORS["graphite_deep"]};
    }}
    QAbstractScrollArea::corner {{
        background: {COLORS["graphite_deep"]};
        border: 0;
    }}
    QSplitter::handle {{
        background: {COLORS["graphite_deep"]};
    }}
    QSplitter::handle:hover {{
        background: {COLORS["border_strong"]};
    }}
    QToolTip {{
        background: {COLORS["graphite_raised"]};
        color: {COLORS["text"]};
        border: 1px solid {COLORS["lime"]};
        padding: 4px;
    }}
    QWidget:disabled, QAbstractItemView:disabled {{
        color: {COLORS["subtle"]};
        background: {COLORS["graphite_deep"]};
        border-color: {COLORS["border_subtle"]};
    }}
    QFrame#metricStrip, QFrame#runtimeMetricStrip {{
        background: {COLORS["graphite_deep"]};
        border: 1px solid {COLORS["border"]};
        border-radius: {LAYOUT["radius_md"]}px;
    }}
    QFrame#metricCell {{
        background: {COLORS["graphite_mid"]};
        border: 1px solid {COLORS["border_subtle"]};
        border-radius: {LAYOUT["radius_sm"]}px;
    }}
    QFrame#serviceDetailCard {{
        background: {COLORS["surface"]};
        border: 1px solid {COLORS["border"]};
        border-radius: {LAYOUT["radius_md"]}px;
    }}
    QFrame#detailRow {{
        background: {COLORS["graphite_inset"]};
        border: 0;
        border-bottom: 1px solid {COLORS["border_subtle"]};
        border-radius: 0;
    }}
    QFrame#denseToolbar, QFrame#actionDock, QFrame#runtimeActionDock,
    QFrame#runtimeWorkspaceFrame, QFrame#activityCommandToolbar,
    QFrame#activityInvestigationControls {{
        background: {COLORS["graphite_mid"]};
        border: 1px solid {COLORS["border"]};
        border-radius: {LAYOUT["radius_md"]}px;
    }}
    QFrame#runtimeActionDock {{
        background: {COLORS["panel_raised"]};
        border-color: {COLORS["border_strong"]};
    }}
    QFrame#pageHeader {{
        background: transparent;
        border: 0;
    }}
    QFrame#workspaceInspectorDetailGrid {{
        background: {COLORS["graphite_mid"]};
        border: 1px solid {COLORS["border_subtle"]};
        border-radius: {LAYOUT["radius_sm"]}px;
    }}
    QLabel[role="inspectorValue"] {{
        color: {COLORS["lime"]};
        font-weight: 700;
    }}
    QFrame#inspectorSurface, QFrame#workspaceLogsInspectorFrame,
    QFrame#activityInputSurface, QFrame#emptySurface {{
        background: {COLORS["graphite_inset"]};
        border: 1px solid {COLORS["border"]};
        border-radius: {LAYOUT["radius_md"]}px;
    }}
    QLabel[role="metricLabel"], QLabel[role="detailLabel"] {{
        color: {COLORS["muted"]};
        font-size: {LAYOUT["font_meta"]}px;
    }}
    QLabel[role="metricValue"], QLabel[role="detailValue"] {{
        color: {COLORS["text"]};
        font-weight: 700;
    }}
    QLabel[role="pill"] {{
        color: {COLORS["text"]};
        background: {COLORS["surface_3"]};
        border: 1px solid {COLORS["border"]};
        border-radius: 10px;
    }}
    QLabel[role="pill"][state="loading"] {{
        color: {COLORS["muted"]};
    }}
    QLabel[role="pill"][state="error"] {{
        color: {COLORS["danger"]};
        border-color: {COLORS["danger"]};
    }}
    QLabel[role="pill"][state="ready"], QLabel[role="pill"][state="success"] {{
        color: {COLORS["success"]};
        border-color: {COLORS["success"]};
    }}
    QLabel[role="pill"][state="warning"], QLabel[role="pill"][state="warn"] {{
        color: {COLORS["warning"]};
        border-color: {COLORS["warning"]};
    }}
    QLabel[role="pill"][state="stopped"] {{
        color: {COLORS["subtle"]};
        border-color: {COLORS["border_strong"]};
    }}
    QLabel[role="footerStatus"] {{
        color: {COLORS["muted"]};
        font-size: {LAYOUT["font_meta"]}px;
    }}
    QPushButton:focus, QLineEdit:focus, QComboBox:focus, QTableView:focus,
    QTextEdit:focus, QTextBrowser:focus, QPlainTextEdit:focus, QTabBar::tab:focus {{
        border: 2px solid {COLORS["lime"]};
    }}
    """
