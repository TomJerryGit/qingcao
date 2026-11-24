# -*- coding: utf-8 -*-
"""给 QDockWidget 安装带「✕」的标题栏。"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDockWidget, QHBoxLayout, QLabel, QToolButton, QWidget


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
    dock.setTitleBarWidget(bar)
    return close_btn
