#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""面包屑导航控件"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class BreadcrumbBar(QWidget):
    """面包屑导航栏"""

    clicked = pyqtSignal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BreadcrumbBar")
        self.setFixedHeight(28)

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(8, 2, 8, 2)
        self.layout.setSpacing(2)

        self.setStyleSheet("""
            QWidget#BreadcrumbBar {
                background-color: #252526;
                border-bottom: 1px solid #3c3c3c;
            }
            QPushButton {
                background-color: transparent;
                color: #cccccc;
                border: none;
                padding: 3px 8px;
                font-size: 12px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #3c3c3c;
                color: #ffffff;
            }
            QLabel {
                color: #666666;
                font-size: 12px;
                padding: 0 2px;
            }
        """)

        self._buttons = []

    def update_path(self, file_name, symbols):
        """更新路径"""
        # 清空旧内容
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._buttons = []

        # 文件按钮
        if file_name:
            file_btn = QPushButton("📄 " + file_name)
            file_btn.setCursor(Qt.PointingHandCursor)
            file_btn.clicked.connect(
                lambda: self.clicked.emit(file_name, 0)
            )
            self.layout.addWidget(file_btn)
            self._buttons.append(file_btn)

        # 符号路径
        for name, line in symbols or []:
            sep = QLabel("›")
            self.layout.addWidget(sep)

            btn = QPushButton(name)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(
                lambda checked=False, l=line: self.clicked.emit(name, l)
            )
            self.layout.addWidget(btn)
            self._buttons.append(btn)

        self.layout.addStretch()

    def clear(self):
        """清空"""
        self.update_path("", [])