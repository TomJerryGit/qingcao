# -*- coding: utf-8 -*-
"""重构助手对话框"""
import difflib
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton,
    QLabel, QLineEdit, QSplitter, QWidget, QTabWidget,
    QListWidget, QListWidgetItem, QMessageBox, QApplication
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor, QTextCharFormat, QTextCursor


class DiffViewer(QWidget):
    """简化的并排 diff 视图"""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # 左侧
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("原代码"))
        self.left_view = QPlainTextEdit()
        self.left_view.setReadOnly(True)
        self.left_view.setFont(QFont("Consolas", 10))
        left_layout.addWidget(self.left_view)
        layout.addWidget(left_widget)

        # 右侧
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("重构后"))
        self.right_view = QPlainTextEdit()
        self.right_view.setReadOnly(True)
        self.right_view.setFont(QFont("Consolas", 10))
        right_layout.addWidget(self.right_view)
        layout.addWidget(right_widget)

    def set_diff(self, left_text, right_text):
        """设置对比"""
        self.left_view.setPlainText(left_text)
        self.right_view.setPlainText(right_text)
        self._highlight_diff(left_text, right_text)

    def _highlight_diff(self, left_text, right_text):
        """高亮差异"""
        left_lines = left_text.splitlines()
        right_lines = right_text.splitlines()

        matcher = difflib.SequenceMatcher(
            None, left_lines, right_lines
        )

        # 左侧：删除行标红
        cursor = self.left_view.textCursor()
        cursor.movePosition(QTextCursor.Start)
        fmt_del = QTextCharFormat()
        fmt_del.setBackground(QColor("#4a1e1e"))
        fmt_del.setForeground(QColor("#ff8888"))

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag in ('delete', 'replace'):
                for i in range(i1, i2):
                    cursor = self._line_cursor(self.left_view, i)
                    cursor.select(QTextCursor.LineUnderCursor)
                    cursor.mergeCharFormat(fmt_del)

        # 右侧：新增行标绿
        fmt_add = QTextCharFormat()
        fmt_add.setBackground(QColor("#1e4a1e"))
        fmt_add.setForeground(QColor("#88ff88"))

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag in ('insert', 'replace'):
                for j in range(j1, j2):
                    cursor = self._line_cursor(self.right_view, j)
                    cursor.select(QTextCursor.LineUnderCursor)
                    cursor.mergeCharFormat(fmt_add)

    def _line_cursor(self, view, line_num):
        cursor = view.textCursor()
        cursor.movePosition(QTextCursor.Start)
        cursor.movePosition(
            QTextCursor.Down, QTextCursor.MoveAnchor, line_num
        )
        return cursor


class RefactorDialog(QDialog):
    """重构助手对话框"""

    def __init__(self, main_window, ai_client,
                 code, language="python", parent=None):
        super().__init__(parent or main_window)
        self.setWindowTitle("AI 重构助手")
        self.resize(1100, 700)

        self.main_window = main_window
        self.language = language

        from core.refactor_session import RefactorSession
        self.session = RefactorSession(ai_client, code, language)

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # 顶部：会话信息
        top = QHBoxLayout()
        self.info_label = QLabel(
            "会话已开始 · 输入需求让 AI 帮你重构"
        )
        self.info_label.setStyleSheet("color: #888; padding: 4px;")
        top.addWidget(self.info_label)
        top.addStretch()

        clear_btn = QPushButton("🔄 重置")
        clear_btn.clicked.connect(self._on_reset)
        top.addWidget(clear_btn)

        layout.addLayout(top)

        # 主区域：左右分割
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：对话历史
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(QLabel("对话历史"))
        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self._on_history_clicked)
        left_layout.addWidget(self.history_list)

        splitter.addWidget(left_widget)

        # 右侧：diff 视图
        self.diff_viewer = DiffViewer()
        splitter.addWidget(self.diff_viewer)

        splitter.setSizes([300, 800])
        layout.addWidget(splitter, 1)

        # 说明区
        layout.addWidget(QLabel("AI 说明:"))
        self.explanation_view = QPlainTextEdit()
        self.explanation_view.setReadOnly(True)
        self.explanation_view.setMaximumHeight(100)
        layout.addWidget(self.explanation_view)

        # 底部：输入
        bottom = QHBoxLayout()

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText(
            "输入你的需求，例如："
            "\"改成函数式风格\" / \"添加类型注解\" / \"简化逻辑\""
        )
        self.input_edit.returnPressed.connect(self._on_send)
        bottom.addWidget(self.input_edit, 1)

        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self._on_send)
        bottom.addWidget(self.send_btn)

        self.accept_btn = QPushButton("✓ 接受当前")
        self.accept_btn.setStyleSheet(
            "background-color: #7ec850; color: white;"
        )
        self.accept_btn.clicked.connect(self._on_accept)
        self.accept_btn.setEnabled(False)
        bottom.addWidget(self.accept_btn)

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
            }
            QLineEdit {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 6px;
            }
            QLineEdit:focus { border-color: #007acc; }
            QListWidget {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-bottom: 1px solid #2d2d2d;
            }
            QListWidget::item:hover { background-color: #2a2d2e; }
            QListWidget::item:selected { background-color: #094771; }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #1177bb; }
            QPushButton:disabled {
                background-color: #3c3c3c;
                color: #666;
            }
        """)

    def _on_send(self):
        """发送请求"""
        text = self.input_edit.text().strip()
        if not text:
            return

        self.input_edit.clear()
        self.send_btn.setEnabled(False)
        self.info_label.setText("AI 正在思考...")

        # 添加用户消息
        item = QListWidgetItem("👤 你: " + text)
        item.setForeground(QColor("#7ec850"))
        self.history_list.addItem(item)

        # 发送请求
        self.session.send_request(
            text,
            callback=self._on_response,
            error_callback=self._on_error,
        )

    def _on_response(self, iteration):
        """AI 响应"""
        self.info_label.setText(
            "迭代 #%d · %d 字符 · 输入需求继续"
            % (iteration.iteration, len(iteration.proposed_code))
        )

        # 显示对比
        self.diff_viewer.set_diff(
            iteration.original_code,
            iteration.proposed_code
        )

        # 显示说明
        self.explanation_view.setPlainText(
            iteration.ai_explanation or "(无说明)"
        )

        # 添加历史项
        item = QListWidgetItem(
            "🤖 AI 迭代 #%d" % iteration.iteration
        )
        item.setForeground(QColor("#4dabf7"))
        item.setData(Qt.UserRole, iteration.iteration - 1)
        self.history_list.addItem(item)
        self.history_list.setCurrentItem(item)

        self.send_btn.setEnabled(True)
        self.accept_btn.setEnabled(True)

    def _on_error(self, err):
        """错误"""
        self.info_label.setText("错误: " + err)
        self.send_btn.setEnabled(True)

    def _on_history_clicked(self, item):
        """点击历史项"""
        idx = item.data(Qt.UserRole)
        if idx is None:
            return

        iterations = self.session.get_all_iterations()
        if 0 <= idx < len(iterations):
            it = iterations[idx]
            self.diff_viewer.set_diff(
                it.original_code, it.proposed_code
            )
            self.explanation_view.setPlainText(
                it.ai_explanation or "(无说明)"
            )
            self.accept_btn.setEnabled(True)

    def _on_accept(self):
        """接受当前迭代"""
        item = self.history_list.currentItem()
        if not item:
            return

        idx = item.data(Qt.UserRole)
        if idx is None:
            return

        self.session.accept_iteration(idx)
        self.info_label.setText(
            "✓ 已接受迭代 #%d" % (idx + 1)
        )

        # 更新代码到编辑器
        if self.main_window:
            proxy = self.main_window.tabs.current_proxy()
            if proxy and proxy.sc:
                try:
                    proxy.sc.replaceSelectedText(
                        self.session.get_current_code()
                    )
                except Exception:
                    pass

    def _on_reset(self):
        """重置"""
        reply = QMessageBox.question(
            self, "重置", "确定重置重构会话？"
        )
        if reply != QMessageBox.Yes:
            return

        from core.refactor_session import RefactorSession
        self.session = RefactorSession(
            self.session.ai_client,
            self.session.original_code,
            self.language,
        )
        self.history_list.clear()
        self.explanation_view.clear()
        self.info_label.setText("会话已重置")