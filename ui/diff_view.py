# -*- coding: utf-8 -*-
"""文件差异对比视图"""
import difflib
import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


class DiffViewDialog(QDialog):
    """差异对比对话框"""

    def __init__(self, parent=None, left_path="", right_path=""):
        super().__init__(parent)
        self.setWindowTitle("文件对比")
        self.resize(1100, 700)

        self.left_path = left_path
        self.right_path = right_path

        self._build_ui()
        self._apply_style()

        if left_path and right_path:
            self._load_files()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # 顶部：文件选择
        top = QHBoxLayout()

        top.addWidget(QLabel("左:"))
        self.left_edit = QLabel(self.left_path or "(未选择)")
        self.left_edit.setStyleSheet(
            "background-color: #3c3c3c; padding: 4px 8px; "
            "border-radius: 3px; color: #d4d4d4;"
        )
        top.addWidget(self.left_edit, 1)

        left_btn = QPushButton("选择...")
        left_btn.clicked.connect(self._pick_left)
        top.addWidget(left_btn)

        top.addWidget(QLabel("右:"))
        self.right_edit = QLabel(self.right_path or "(未选择)")
        self.right_edit.setStyleSheet(
            "background-color: #3c3c3c; padding: 4px 8px; "
            "border-radius: 3px; color: #d4d4d4;"
        )
        top.addWidget(self.right_edit, 1)

        right_btn = QPushButton("选择...")
        right_btn.clicked.connect(self._pick_right)
        top.addWidget(right_btn)

        compare_btn = QPushButton("🔍 对比")
        compare_btn.clicked.connect(self._load_files)
        top.addWidget(compare_btn)

        layout.addLayout(top)

        # 中间：并排视图
        splitter = QSplitter(Qt.Horizontal)

        # 左侧
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("原文件"))
        self.left_view = QPlainTextEdit()
        self.left_view.setReadOnly(True)
        self.left_view.setFont(QFont("Consolas", 10))
        left_layout.addWidget(self.left_view)
        splitter.addWidget(left_widget)

        # 右侧
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("新文件"))
        self.right_view = QPlainTextEdit()
        self.right_view.setReadOnly(True)
        self.right_view.setFont(QFont("Consolas", 10))
        right_layout.addWidget(self.right_view)
        splitter.addWidget(right_widget)

        layout.addWidget(splitter, 1)

        # 底部：统计
        bottom = QHBoxLayout()

        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: #888;")
        bottom.addWidget(self.stats_label)

        bottom.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)

        layout.addLayout(bottom)

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #d4d4d4; }
            QLabel { color: #d4d4d4; }
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                font-family: Consolas, monospace;
                font-size: 10pt;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #1177bb; }
            QSplitter::handle { background-color: #3c3c3c; }
        """)

    def _pick_left(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择左文件")
        if path:
            self.left_path = path
            self.left_edit.setText(path)

    def _pick_right(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择右文件")
        if path:
            self.right_path = path
            self.right_edit.setText(path)

    def _load_files(self):
        """加载并对比"""
        if not self.left_path or not self.right_path:
            QMessageBox.warning(self, "提示", "请先选择两个文件")
            return

        try:
            with open(self.left_path, encoding='utf-8',
                      errors='replace') as f:
                left_text = f.read()
            with open(self.right_path, encoding='utf-8',
                      errors='replace') as f:
                right_text = f.read()
        except Exception as e:
            QMessageBox.warning(self, "读取失败", str(e))
            return

        # 显示原始文本
        self.left_view.setPlainText(left_text)
        self.right_view.setPlainText(right_text)

        # 计算差异
        left_lines = left_text.splitlines()
        right_lines = right_text.splitlines()

        matcher = difflib.SequenceMatcher(None, left_lines, right_lines)

        added = 0
        removed = 0
        modified = 0

        # 高亮左侧
        cursor = self.left_view.textCursor()
        cursor.movePosition(QTextCursor.Start)
        left_fmt_removed = QTextCharFormat()
        left_fmt_removed.setBackground(QColor("#4a1e1e"))
        left_fmt_removed.setForeground(QColor("#ff8888"))

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'delete' or tag == 'replace':
                for i in range(i1, i2):
                    cursor = self._line_cursor(self.left_view, i)
                    cursor.select(QTextCursor.LineUnderCursor)
                    cursor.mergeCharFormat(left_fmt_removed)
                removed += (i2 - i1)

        # 高亮右侧
        right_fmt_added = QTextCharFormat()
        right_fmt_added.setBackground(QColor("#1e4a1e"))
        right_fmt_added.setForeground(QColor("#88ff88"))

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'insert' or tag == 'replace':
                for j in range(j1, j2):
                    cursor = self._line_cursor(self.right_view, j)
                    cursor.select(QTextCursor.LineUnderCursor)
                    cursor.mergeCharFormat(right_fmt_added)
                added += (j2 - j1)

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'replace':
                modified += max(i2 - i1, j2 - j1)

        # 相似度
        ratio = matcher.ratio()

        self.stats_label.setText(
            "相似度: %.1f%% · 新增 %d 行 · 删除 %d 行 · 修改 %d 行"
            % (ratio * 100, added, removed, modified)
        )

    def _line_cursor(self, view, line_num):
        """获取某行的光标"""
        cursor = view.textCursor()
        cursor.movePosition(QTextCursor.Start)
        cursor.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor,
                             line_num)
        return cursor