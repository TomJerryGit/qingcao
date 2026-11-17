# -*- coding: utf-8 -*-
"""AI 宿主面板：隔离插件流式输出展示。"""

from PyQt5.QtWidgets import (
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class AIHostPanel(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("AI 输出", parent)
        self.setObjectName("AIHostPanel")
        body = QWidget(self)
        layout = QVBoxLayout(body)
        row = QHBoxLayout()
        self.session_combo = QComboBox()
        self.session_combo.setEditable(True)
        self.session_combo.addItem("default")
        row.addWidget(self.session_combo, 1)
        self.new_session_btn = QPushButton("新会话")
        self.new_session_btn.clicked.connect(self._new_session)
        row.addWidget(self.new_session_btn)
        layout.addLayout(row)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        layout.addWidget(self.view)
        self.setWidget(body)
        self.session_combo.currentTextChanged.connect(lambda *_: self._select_session())

    def _new_session(self):
        name = "s%d" % (self.session_combo.count() + 1)
        self.session_combo.addItem(name)
        self.session_combo.setCurrentText(name)
        self._select_session()

    def _select_session(self):
        from core.ai_service import get_ai_service

        get_ai_service().set_current_session(self.session_combo.currentText())

    def clear(self):
        self.view.clear()

    def append_chunk(self, text):
        cursor = self.view.textCursor()
        cursor.movePosition(cursor.End)
        cursor.insertText(str(text))
        self.view.setTextCursor(cursor)
        self.view.ensureCursorVisible()
