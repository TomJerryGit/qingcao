# -*- coding: utf-8 -*-
"""Markdown 预览插件"""
import os
from PyQt5.QtWidgets import QDockWidget, QTextBrowser
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from app.plugins import PluginBase


class MarkdownPanel(QDockWidget):
    """Markdown 预览面板"""

    def __init__(self, parent=None):
        super().__init__("Markdown 预览", parent)
        self.setObjectName("MarkdownPreviewPanel")

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setFont(QFont("Microsoft YaHei", 11))

        self.setWidget(self.browser)
        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet("""
            QDockWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QDockWidget::title {
                background-color: #2d2d2d;
                padding: 4px 8px;
            }
            QTextBrowser {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                padding: 12px;
                selection-background-color: #264f78;
            }
        """)

    def render(self, text):
        """渲染"""
        try:
            self.browser.setMarkdown(text)
        except Exception as e:
            self.browser.setPlainText(f"渲染失败: {e}")


class Plugin(PluginBase):
    NAME = "markdown_preview"
    VERSION = "1.0.0"
    DESCRIPTION = "Markdown 预览"
    AUTHOR = "hedongwei"

    def on_activate(self):
        self.api.log("Markdown 预览插件已激活")
        self._panel = None

        # C2: 避开主窗口的 Ctrl+Shift+M（回放宏）
        self.api.add_menu(
            "视图/Markdown 预览",
            self.toggle_preview,
            shortcut="Ctrl+Alt+M"
        )

        # 定时刷新
        self._timer = QTimer()
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

    def on_deactivate(self):
        if self._timer:
            self._timer.stop()
        if self._panel:
            self._panel.close()

    def toggle_preview(self):
        """切换预览"""
        if not self._panel:
            self._panel = MarkdownPanel(self.api.win)
            # 修复: 使用 Qt 枚举而非裸 int
            self.api.win.addDockWidget(
                Qt.RightDockWidgetArea, self._panel
            )

        visible = not self._panel.isVisible()
        self._panel.setVisible(visible)
        if visible:
            self._refresh()

    def _refresh(self):
        """刷新"""
        if not self._panel or not self._panel.isVisible():
            return

        try:
            filepath = self.api.get_current_filepath()
            if not filepath or not filepath.lower().endswith(
                ('.md', '.markdown')
            ):
                return

            text = self.api.get_current_text()
            self._panel.render(text)
        except Exception:
            pass