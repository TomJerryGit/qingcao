# -*- coding: utf-8 -*-
"""Git 差异视图"""
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QDialog, QPlainTextEdit, QPushButton, QVBoxLayout


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

        # 修复 B5：避免 diff 重复显示
        # 原实现先 setPlainText 全文，再 appendHtml 逐行加色，
        # 结果内容被写了两遍。改成只 append 一次。
        # 同时用 html.escape 转义特殊字符，避免 HTML 渲染问题。
        import html as html_mod
        if not diff_text:
            view.setPlainText("(无差异)")
        else:
            for line in diff_text.split('\n'):
                escaped = html_mod.escape(line)
                if line.startswith('+') and not line.startswith('+++'):
                    view.appendHtml(
                        f'<span style="color:#7ec850;">{escaped}</span>'
                    )
                elif line.startswith('-') and not line.startswith('---'):
                    view.appendHtml(
                        f'<span style="color:#f14c4c;">{escaped}</span>'
                    )
                elif line.startswith('@@'):
                    view.appendHtml(
                        f'<span style="color:#569cd6;">{escaped}</span>'
                    )
                else:
                    view.appendPlainText(line)

        layout.addWidget(view)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)