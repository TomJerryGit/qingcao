# -*- coding: utf-8 -*-
"""根据主题生成面板 QSS（搜索/性能监控等宿主面板）。"""


def panel_qss(theme) -> str:
    c = theme.colors
    g = lambda k, d: getattr(c, k, d)
    panel_bg = g("panel_bg", g("background", "#252526"))
    panel_fg = g("panel_fg", g("foreground", "#d4d4d4"))
    bg = g("background", "#1e1e1e")
    fg = g("foreground", "#d4d4d4")
    border = g("border", "#3c3c3c")
    input_bg = g("input_bg", "#3c3c3c")
    input_fg = g("input_fg", fg)
    input_border = g("input_border", border)
    accent = g("accent", "#0e639c")
    button_bg = g("button_bg", accent)
    button_fg = g("button_fg", "#ffffff")
    button_hover = g("button_hover", accent)
    title_bg = g("menubar_bg", panel_bg)
    title_fg = g("menubar_fg", panel_fg)
    return f"""
QDockWidget {{ background: {panel_bg}; color: {panel_fg}; }}
QDockWidget::title {{ background: {title_bg}; color: {title_fg}; padding: 4px 8px; }}
QLabel {{ color: {panel_fg}; padding: 2px; }}
QLineEdit, QComboBox {{
    background: {input_bg}; color: {input_fg};
    border: 1px solid {input_border}; border-radius: 3px; padding: 3px 6px;
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {g("input_focus", accent)}; }}
QComboBox QAbstractItemView {{
    background: {input_bg}; color: {input_fg};
    selection-background-color: {accent}; selection-color: {button_fg};
}}
QPushButton {{
    background: {button_bg}; color: {button_fg}; border: none;
    border-radius: 3px; padding: 4px 10px;
}}
QPushButton:hover {{ background: {button_hover}; }}
QCheckBox {{ color: {panel_fg}; spacing: 4px; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; background: {input_bg};
    border: 1px solid {input_border}; border-radius: 2px;
}}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}
QGroupBox {{
    color: {panel_fg}; border: 1px solid {border};
    border-radius: 4px; margin-top: 10px; padding-top: 8px; font-weight: bold;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; }}
QTreeWidget, QTreeView, QTextEdit, QPlainTextEdit {{
    background: {bg}; color: {fg}; border: 1px solid {border};
}}
QTreeWidget::item:selected, QTreeView::item:selected {{
    background: {accent}; color: {button_fg};
}}
"""
