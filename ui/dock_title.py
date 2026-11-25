# -*- coding: utf-8 -*-
"""给 QDockWidget 安装带「✕」的标题栏。"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDockWidget, QHBoxLayout, QLabel, QToolButton, QWidget


def _theme_foreground(widget):
    try:
        from infrastructure.theme_loader import ThemeLoader

        win = widget.window()
        name = getattr(win, "_current_theme_name", "dark_night")
        theme = ThemeLoader().load_by_name(name)
        if theme is not None:
            return getattr(theme.colors, "foreground", "#d4d4d4")
    except Exception:
        pass
    return "#d4d4d4"


def install_close_button(dock: QDockWidget, title: str = ""):
    dock.setFeatures(
        QDockWidget.DockWidgetClosable
        | QDockWidget.DockWidgetMovable
        | QDockWidget.DockWidgetFloatable
    )
    bar = QWidget(dock)
    bar.setObjectName("dockTitleBar")
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(8, 2, 4, 2)
    layout.setSpacing(4)
    label = QLabel(title or dock.windowTitle(), bar)
    label.setObjectName("dockTitleLabel")
    layout.addWidget(label)
    layout.addStretch(1)
    close_btn = QToolButton(bar)
    close_btn.setText("✕")
    close_btn.setToolTip("关闭")
    close_btn.setAccessibleName("关闭" + (title or dock.windowTitle()))
    close_btn.setAutoRaise(True)
    close_btn.clicked.connect(dock.close)
    layout.addWidget(close_btn)

    original_refresh = getattr(dock, "refresh_theme", None)

    def _refresh(theme=None):
        fg = _theme_foreground(dock)
        if theme is not None:
            try:
                fg = theme.colors.foreground
            except Exception:
                pass
        bar.setStyleSheet(
            "QWidget{background: transparent;} "
            "QLabel{color: %s; font-weight: 600;} "
            "QToolButton{color: %s; border: none; padding: 0 4px;}" % (fg, fg)
        )
        if callable(original_refresh):
            try:
                original_refresh(theme)
            except Exception:
                pass

    _refresh()
    dock.refresh_theme = _refresh
    dock.setTitleBarWidget(bar)
    return close_btn
