# -*- coding: utf-8 -*-
"""三方合并对话框"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.file_merge import ThreeWayMerger


class FileMergeDialog(QDialog):
    """三方合并对话框"""

    def __init__(self, filepath, original, local, remote, parent=None):
        super().__init__(parent)
        self.setWindowTitle("合并外部变更: " + filepath)
        self.resize(1000, 700)

        self.filepath = filepath
        self.original_text = original
        self.local_text = local
        self.remote_text = remote

        # 执行合并
        merger = ThreeWayMerger()
        result = merger.merge(original, local, remote)

        self.merged_text = result['merged']
        self.conflicts = result['conflicts']
        self.auto_merged = result['auto_merged']

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # 信息
        info = QLabel()
        if self.auto_merged:
            info.setText(
                "✅ 已自动合并。请检查合并结果后确认。"
            )
            info.setStyleSheet("color: #7ec850; padding: 8px;")
        else:
            info.setText(
                "⚠ 检测到 %d 处冲突，请手动解决。" % len(self.conflicts)
            )
            info.setStyleSheet("color: #f0ad4e; padding: 8px;")
        layout.addWidget(info)

        # 三方视图
        splitter = QSplitter(Qt.Horizontal)

        # 编辑器
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("编辑器内容（本地）"))
        self.local_view = QPlainTextEdit()
        self.local_view.setPlainText(self.local_text)
        self.local_view.setReadOnly(True)
        self.local_view.setFont(QFont("Consolas", 10))
        left_layout.addWidget(self.local_view)
        splitter.addWidget(left_widget)

        # 磁盘
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("磁盘内容（外部）"))
        self.remote_view = QPlainTextEdit()
        self.remote_view.setPlainText(self.remote_text)
        self.remote_view.setReadOnly(True)
        self.remote_view.setFont(QFont("Consolas", 10))
        right_layout.addWidget(self.remote_view)
        splitter.addWidget(right_widget)

        splitter.setSizes([500, 500])
        layout.addWidget(splitter, 1)

        # 合并结果
        layout.addWidget(QLabel("合并结果（可编辑）:"))
        self.merged_view = QPlainTextEdit()
        self.merged_view.setPlainText(self.merged_text)
        self.merged_view.setFont(QFont("Consolas", 10))
        layout.addWidget(self.merged_view, 1)

        # 底部按钮
        btn_layout = QHBoxLayout()

        accept_btn = QPushButton("✓ 接受合并结果")
        accept_btn.setStyleSheet(
            "background-color: #7ec850; color: white;"
        )
        accept_btn.clicked.connect(self._on_accept)
        btn_layout.addWidget(accept_btn)

        discard_btn = QPushButton("✗ 放弃我的修改")
        discard_btn.clicked.connect(self._on_discard)
        btn_layout.addWidget(discard_btn)

        keep_btn = QPushButton("✗ 保留我的修改")
        keep_btn.clicked.connect(self._on_keep_local)
        btn_layout.addWidget(keep_btn)

        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

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
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #1177bb; }
        """)

    def _on_accept(self):
        """接受合并结果"""
        self.merged_text = self.merged_view.toPlainText()
        self.accept()

    def _on_discard(self):
        """放弃本地修改，用磁盘内容"""
        self.merged_text = self.remote_text
        self.accept()

    def _on_keep_local(self):
        """保留本地修改，忽略磁盘内容"""
        self.merged_text = self.local_text
        self.accept()

    def get_merged_text(self):
        """获取合并结果"""
        return self.merged_text