# -*- coding: utf-8 -*-
"""Git 面板"""
from PyQt5.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget,
    QTreeWidgetItem, QPushButton, QPlainTextEdit, QLabel, QMenu,
    QInputDialog, QMessageBox, QSplitter, QToolButton
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor

from core.git_client import GitClient


class GitPanel(QDockWidget):
    """Git 状态与控制面板"""

    def __init__(self, main_window=None, parent=None):
        super().__init__("Git", parent or main_window)
        self.main_window = main_window
        self.setObjectName("GitPanel")

        self.git = None
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 工具条
        top = QHBoxLayout()

        self.branch_label = QLabel("分支: -")
        self.branch_label.setStyleSheet("color: #7ec850; font-weight: bold;")
        top.addWidget(self.branch_label)

        top.addStretch()

        for text, tip, slot in [
            ("??", "刷新", self.refresh),
            ("?", "推送", self._push),
            ("?", "拉取", self._pull),
            ("?", "提交", self._commit),
        ]:
            btn = QToolButton()
            btn.setText(text)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            top.addWidget(btn)

        layout.addLayout(top)

        # 变更列表
        layout.addWidget(QLabel("变更:"))
        self.change_tree = QTreeWidget()
        self.change_tree.setHeaderLabels(["状态", "文件"])
        self.change_tree.setColumnWidth(0, 60)
        self.change_tree.itemDoubleClicked.connect(self._on_show_diff)
        layout.addWidget(self.change_tree, 1)

        # Diff 视图
        layout.addWidget(QLabel("差异:"))
        self.diff_view = QPlainTextEdit()
        self.diff_view.setReadOnly(True)
        self.diff_view.setFont(QFont("Consolas", 10))
        self.diff_view.setMaximumHeight(250)
        layout.addWidget(self.diff_view)

        self.setWidget(container)


    def refresh_theme(self, theme):
        """主题变更时刷新样式（v3.0）"""
        try:
            from infrastructure.theme_loader import adapt_qss_colors
            # 保存原始 QSS（只保存一次）
            if not hasattr(self, '_original_qss') or not self._original_qss:
                self._original_qss = self.styleSheet()
            if self._original_qss:
                qss = adapt_qss_colors(self._original_qss, theme)
                self.setStyleSheet(qss)
        except Exception as e:
            print(f"[{self.__class__.__name__}] refresh_theme 失败: {e}")

    def _apply_style(self):
        self.setStyleSheet("""
            QTreeWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                font-size: 12px;
            }
            QTreeWidget::item {
                padding: 3px;
            }
            QTreeWidget::item:selected {
                background-color: #094771;
            }
            QPlainTextEdit {
                background-color: #0d0d0d;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                font-family: Consolas, monospace;
                font-size: 10pt;
            }
            QLabel {
                color: #d4d4d4;
                padding: 2px;
            }
            QToolButton {
                background-color: transparent;
                color: #d4d4d4;
                border: none;
                padding: 4px 8px;
                font-size: 14px;
            }
            QToolButton:hover {
                background-color: #3c3c3c;
                border-radius: 3px;
            }
        """)

    def set_root(self, path):
        """设置 Git 根目录"""
        root = self.git.find_root(path) if self.git else None
        self.git = GitClient(path)
        root = self.git.find_root(path)
        if root:
            self.git = GitClient(root)
            self.refresh()

    def refresh(self):
        """刷新状态"""
        if not self.git or not self.git.is_repo():
            self.branch_label.setText("分支: (不是 Git 仓库)")
            self.change_tree.clear()
            return

        self.branch_label.setText("分支: " + self.git.current_branch())

        self.change_tree.clear()
        status = self.git.status()

        STATUS_NAMES = {
            'M ': '已暂存修改',
            ' M': '已修改',
            'MM': '已修改+暂存',
            'A ': '已暂存新增',
            '??': '未跟踪',
            'D ': '已暂存删除',
            ' D': '已删除',
            'R ': '已重命名',
        }

        for filepath, code in status.items():
            display = STATUS_NAMES.get(code, code)
            item = QTreeWidgetItem(self.change_tree)
            item.setText(0, display)
            item.setText(1, filepath)
            item.setData(0, Qt.UserRole, filepath)

            # 颜色
            if code.startswith('?'):
                item.setForeground(0, QColor("#808080"))
            elif 'M' in code:
                item.setForeground(0, QColor("#E5A72D"))
            elif 'A' in code:
                item.setForeground(0, QColor("#6A9955"))
            elif 'D' in code:
                item.setForeground(0, QColor("#F14C4C"))

    def _on_show_diff(self, item, column):
        """显示差异"""
        filepath = item.data(0, Qt.UserRole)
        if not filepath:
            return

        diff = self.git.diff(filepath)
        if not diff:
            diff = self.git.diff_staged(filepath)

        self.diff_view.clear()
        # 简单着色
        for line in diff.splitlines():
            if line.startswith('+'):
                self.diff_view.appendHtml(
                    '<span style="color:#7ec850;">'
                    + line.replace('<', '&lt;').replace('>', '&gt;')
                    + '</span>'
                )
            elif line.startswith('-'):
                self.diff_view.appendHtml(
                    '<span style="color:#f14c4c;">'
                    + line.replace('<', '&lt;').replace('>', '&gt;')
                    + '</span>'
                )
            elif line.startswith('@@'):
                self.diff_view.appendHtml(
                    '<span style="color:#569cd6;">'
                    + line.replace('<', '&lt;').replace('>', '&gt;')
                    + '</span>'
                )
            else:
                self.diff_view.appendPlainText(line)

    def _push(self):
        if not self.git:
            return
        ok, msg = self.git.push()
        QMessageBox.information(
            self, "推送", "成功" if ok else "失败: " + msg
        )
        self.refresh()

    def _pull(self):
        if not self.git:
            return
        ok, msg = self.git.pull()
        QMessageBox.information(
            self, "拉取", "成功" if ok else "失败: " + msg
        )
        self.refresh()

    def _commit(self):
        if not self.git:
            return
        msg, ok = QInputDialog.getMultiLineText(
            self, "提交", "提交信息:"
        )
        if not ok or not msg.strip():
            return

        # 先暂存所有变更
        for i in range(self.change_tree.topLevelItemCount()):
            item = self.change_tree.topLevelItem(i)
            filepath = item.data(0, Qt.UserRole)
            if filepath:
                self.git.add(filepath)

        ok, err = self.git.commit(msg)
        if ok:
            QMessageBox.information(self, "提交", "提交成功")
        else:
            QMessageBox.warning(self, "提交失败", err)
        self.refresh()