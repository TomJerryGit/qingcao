# -*- coding: utf-8 -*-
"""代码片段编辑器"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLineEdit, QPlainTextEdit, QLabel, QFormLayout,
    QMessageBox, QSplitter, QWidget
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from core.snippets import get_snippet_manager, Snippet


class SnippetEditor(QDialog):
    """代码片段编辑器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("代码片段编辑器")
        self.resize(800, 500)

        self.mgr = get_snippet_manager()
        self._current = None

        self._build_ui()
        self._apply_style()
        self._refresh_list()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Horizontal)

        # 左侧：列表
        left = QWidget()
        left_layout = QVBoxLayout(left)

        self.list_widget = QListWidget()
        self.list_widget.itemSelectionChanged.connect(self._on_select)
        left_layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("➕ 新建")
        add_btn.clicked.connect(self._on_new)
        btn_row.addWidget(add_btn)

        del_btn = QPushButton("🗑 删除")
        del_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(del_btn)

        left_layout.addLayout(btn_row)
        splitter.addWidget(left)

        # 右侧：编辑
        right = QWidget()
        right_layout = QVBoxLayout(right)

        form = QFormLayout()

        self.name_edit = QLineEdit()
        form.addRow("名称:", self.name_edit)

        self.prefix_edit = QLineEdit()
        form.addRow("触发前缀:", self.prefix_edit)

        self.desc_edit = QLineEdit()
        form.addRow("描述:", self.desc_edit)

        self.scope_edit = QLineEdit()
        self.scope_edit.setPlaceholderText("如 python / javascript / 空=所有")
        form.addRow("作用域:", self.scope_edit)

        right_layout.addLayout(form)

        right_layout.addWidget(QLabel("片段内容（支持 ${1:占位符}）："))
        self.body_edit = QPlainTextEdit()
        self.body_edit.setFont(QFont("Consolas", 11))
        right_layout.addWidget(self.body_edit)

        save_btn = QPushButton("💾 保存")
        save_btn.clicked.connect(self._on_save)
        right_layout.addWidget(save_btn)

        splitter.addWidget(right)
        splitter.setSizes([250, 550])

        layout.addWidget(splitter)

        # 底部
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #d4d4d4; }
            QLabel { color: #d4d4d4; }
            QListWidget {
                background-color: #252526; color: #d4d4d4;
                border: 1px solid #3c3c3c;
            }
            QListWidget::item { padding: 4px 8px; }
            QListWidget::item:selected { background-color: #094771; }
            QLineEdit, QPlainTextEdit {
                background-color: #3c3c3c; color: #d4d4d4;
                border: 1px solid #555; border-radius: 3px;
                padding: 4px;
            }
            QLineEdit:focus, QPlainTextEdit:focus { border-color: #007acc; }
            QPushButton {
                background-color: #0e639c; color: white;
                border: none; border-radius: 3px;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #1177bb; }
        """)

    def _refresh_list(self):
        self.list_widget.clear()
        for snippet in sorted(self.mgr.list_all(),
                                key=lambda s: s.prefix):
            item = QListWidgetItem(
                "%s  -  %s" % (snippet.prefix, snippet.name)
            )
            item.setData(Qt.UserRole, snippet.prefix)
            self.list_widget.addItem(item)

    def _on_select(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        prefix = item.data(Qt.UserRole)
        snippet = self.mgr.get(prefix)
        if not snippet:
            return

        self._current = prefix
        self.name_edit.setText(snippet.name)
        self.prefix_edit.setText(snippet.prefix)
        self.desc_edit.setText(snippet.description)
        self.scope_edit.setText(snippet.scope)

        body = snippet.body
        if isinstance(body, list):
            body = "\n".join(body)
        self.body_edit.setPlainText(body)

    def _on_new(self):
        self._current = None
        self.name_edit.clear()
        self.prefix_edit.clear()
        self.desc_edit.clear()
        self.scope_edit.clear()
        self.body_edit.clear()
        self.name_edit.setFocus()

    def _on_save(self):
        prefix = self.prefix_edit.text().strip()
        if not prefix:
            QMessageBox.warning(self, "错误", "触发前缀不能为空")
            return

        snippet = Snippet(
            self.name_edit.text().strip() or prefix,
            prefix,
            self.body_edit.toPlainText(),
            self.desc_edit.text().strip(),
            self.scope_edit.text().strip(),
        )
        self.mgr.add(snippet)
        self._refresh_list()
        QMessageBox.information(self, "成功", "片段已保存")

    def _on_delete(self):
        if not self._current:
            return
        reply = QMessageBox.question(
            self, "确认", "删除片段 '%s'？" % self._current
        )
        if reply == QMessageBox.Yes:
            self.mgr.remove(self._current)
            self._refresh_list()
            self._on_new()