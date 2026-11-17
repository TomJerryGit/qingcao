# -*- coding: utf-8 -*-
"""AI 宿主面板：隔离插件流式输出展示。"""

from PyQt5.QtWidgets import QDockWidget, QPlainTextEdit, QVBoxLayout, QWidget


class AIHostPanel(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("AI 输出", parent)
        self.setObjectName("AIHostPanel")
        body = QWidget(self)
        layout = QVBoxLayout(body)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        layout.addWidget(self.view)
        self.setWidget(body)

    def clear(self):
        self.view.clear()

    def append_chunk(self, text):
        cursor = self.view.textCursor()
        cursor.movePosition(cursor.End)
        cursor.insertText(str(text))
        self.view.setTextCursor(cursor)
        self.view.ensureCursorVisible()
