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
        self.rename_btn = QPushButton("重命名")
        self.rename_btn.clicked.connect(self._rename_session)
        row.addWidget(self.rename_btn)
        self.delete_btn = QPushButton("删除")
        self.delete_btn.clicked.connect(self._delete_session)
        row.addWidget(self.delete_btn)
        layout.addLayout(row)
        self._refresh_sessions("default")
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        layout.addWidget(self.view)
        self.setWidget(body)
        self.session_combo.currentTextChanged.connect(lambda *_: self._select_session())

    def _new_session(self):
        from core.ai_service import get_ai_service

        name = "s%d" % (self.session_combo.count() + 1)
        get_ai_service().set_current_session(name)
        self.session_combo.addItem(name)
        self.session_combo.setCurrentText(name)
        self._select_session()
        self._refresh_sessions(name)

    def _refresh_sessions(self, current=None):
        from core.ai_service import get_ai_service

        service = get_ai_service()
        names = service.session_names() or ["default"]
        if current not in names:
            current = service.current_session()
        if current not in names:
            current = names[0]
        self.session_combo.blockSignals(True)
        self.session_combo.clear()
        self.session_combo.addItems(names)
        self.session_combo.setCurrentText(current)
        self.session_combo.blockSignals(False)
        service.set_current_session(current)

    def _rename_session(self):
        from PyQt5.QtWidgets import QInputDialog

        from core.ai_service import get_ai_service

        service = get_ai_service()
        old = self.session_combo.currentText()
        new, ok = QInputDialog.getText(self, "重命名会话", "新名称:", text=old)
        if not ok or not str(new).strip():
            return
        result = service.rename_session(old, str(new).strip())
        if result.get("ok"):
            self._refresh_sessions(str(new).strip())

    def _delete_session(self):
        from PyQt5.QtWidgets import QMessageBox

        from core.ai_service import get_ai_service

        service = get_ai_service()
        name = self.session_combo.currentText()
        if QMessageBox.question(self, "删除会话", "确定删除会话「%s」？" % name) != QMessageBox.Yes:
            return
        service.delete_session(name)
        self._refresh_sessions()

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
