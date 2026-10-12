# -*- coding: utf-8 -*-
"""Markdown 实时预览"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QDockWidget, QTextBrowser, QVBoxLayout, QWidget


class MarkdownPreview(QDockWidget):
    """Markdown 预览面板"""

    def __init__(self, main_window=None, parent=None):
        super().__init__("Markdown 预览", parent or main_window)
        self.main_window = main_window
        self.setObjectName("MarkdownPreview")
        self.setAllowedAreas(
            Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea |
            Qt.BottomDockWidgetArea
        )

        self._build_ui()
        self._apply_style()

        # 防抖
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._refresh)

    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setFont(QFont("Microsoft YaHei", 11))
        layout.addWidget(self.browser)

        self.setWidget(container)

    def _apply_style(self):
        self.setStyleSheet("""
            QDockWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QDockWidget::title {
                background-color: #2d2d2d;
                padding: 4px 8px;
                border-bottom: 1px solid #3c3c3c;
            }
            QTextBrowser {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                padding: 12px;
                selection-background-color: #264f78;
            }
        """)

    def schedule_refresh(self):
        """调度刷新（防抖）"""
        self._debounce.start()

    def _refresh(self):
        """刷新预览"""
        if not self.main_window:
            return

        try:
            proxy = self.main_window.tabs.current_proxy()
            if not proxy or not proxy.sc:
                self.browser.setMarkdown("# (无活动文件)")
                return

            # 检查是否是 Markdown
            filepath = ""
            if proxy.document:
                filepath = proxy.document.filepath or ""

            if not filepath.lower().endswith(('.md', '.markdown')):
                self.browser.setMarkdown(
                    "# 非 Markdown 文件\n\n当前文件不是 Markdown 格式。"
                )
                return

            text = proxy.sc.text()
            self.browser.setMarkdown(text)

        except Exception as e:
            self.browser.setMarkdown(
                "# 渲染失败\n\n错误: %s" % e
            )

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh()