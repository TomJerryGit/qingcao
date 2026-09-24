# -*- coding: utf-8 -*-
"""Git 差异视图"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QPlainTextEdit, QPushButton
)
from PyQt5.QtGui import QFont


class GitDiffDialog(QDialog):
    """Git 差异对话框"""

    def __init__(self, diff_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Git 差异")
        self.resize(900, 600)

        layout = QVBoxLayout(self)

        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setFont(QFont("Consolas", 10))
        view.setPlainText(diff_text or "(无差异)")

        # 简单着色
        for line in diff_text.split('\n') if diff_text else []:
            if line.startswith('+') and not line.startswith('+++'):
                view.appendHtml(
                    f'<span style="color:#7ec850;">{line}</span>'
                )
            elif line.startswith('-') and not line.startswith('---'):
                view.appendHtml(
                    f'<span style="color:#f14c4c;">{line}</span>'
                )
            elif line.startswith('@@'):
                view.appendHtml(
                    f'<span style="color:#569cd6;">{line}</span>'
                )

        layout.addWidget(view)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)