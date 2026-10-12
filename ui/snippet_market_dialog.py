# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为代码片段市场对话框模块。

职责:
    - 提供片段市场的 UI 界面
    - 拉取远程片段列表（通过 core.snippet_market.SnippetMarketClient）
    - 按语言/关键词过滤
    - 安装选中片段到本地（通过 core.snippets 管理器）

重命名说明（P3-9）:
    - 原文件名为 ui/snippet_market.py，与 core/snippet_market.py 同名，
      容易混淆。已重命名为 ui/snippet_market_dialog.py。
    - 原类名 SnippetMarket 已重命名为 SnippetMarketDialog，
      更清晰地表明这是一个对话框（QDialog 子类）。
    - 依赖的 core.snippet_market 模块保持不变。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.snippet_market import SnippetMarketClient


class SnippetMarketDialog(QDialog):
    """代码片段市场对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("代码片段市场")
        self.resize(700, 500)

        self.client = SnippetMarketClient(self)
        self.client.fetch_completed.connect(self._on_fetch_done)
        self.client.fetch_failed.connect(self._on_fetch_failed)
        self.client.download_completed.connect(self._on_download_done)
        self.client.download_failed.connect(self._on_download_failed)

        self._snippets = []

        self._build_ui()
        self._apply_style()

        # 自动加载
        self.client.fetch_async()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # 顶部
        top = QHBoxLayout()

        top.addWidget(QLabel("语言:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems([
            "全部", "Python", "JavaScript", "TypeScript",
            "SQL", "HTML", "CSS", "Shell"
        ])
        self.lang_combo.currentTextChanged.connect(self._apply_filter)
        top.addWidget(self.lang_combo)

        top.addWidget(QLabel("搜索:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("关键词...")
        self.search_edit.textChanged.connect(self._apply_filter)
        top.addWidget(self.search_edit, 1)

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(lambda: self.client.fetch_async(force=True))
        top.addWidget(refresh_btn)

        layout.addLayout(top)

        # 列表
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_install)
        layout.addWidget(self.list_widget, 1)

        # 状态
        self.status_label = QLabel("加载中...")
        self.status_label.setStyleSheet("color: #888;")
        layout.addWidget(self.status_label)

        # 底部
        bottom = QHBoxLayout()

        install_btn = QPushButton("⬇ 安装选中")
        install_btn.clicked.connect(self._on_install)
        bottom.addWidget(install_btn)

        bottom.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)

        layout.addLayout(bottom)

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #d4d4d4; }
            QLabel { color: #d4d4d4; }
            QListWidget {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 6px 10px;
                border-bottom: 1px solid #2d2d2d;
            }
            QListWidget::item:hover { background-color: #2a2d2e; }
            QListWidget::item:selected { background-color: #094771; }
            QLineEdit, QComboBox {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 4px;
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

    def _on_fetch_done(self, snippets):
        self._snippets = snippets
        self._apply_filter()
        self.status_label.setText("共 %d 个片段" % len(snippets))

    def _on_fetch_failed(self, err):
        self.status_label.setText("加载失败: " + err)

    def _apply_filter(self):
        """应用过滤"""
        lang = self.lang_combo.currentText().lower()
        keyword = self.search_edit.text().strip().lower()

        self.list_widget.clear()

        for s in self._snippets:
            s_lang = s.get('language', '').lower()
            s_name = s.get('name', '').lower()
            s_desc = s.get('description', '').lower()

            if lang != "全部" and lang not in s_lang:
                continue
            if keyword and (keyword not in s_name and keyword not in s_desc):
                continue

            item = QListWidgetItem(
                "📌 %s  [%s]\n    %s" % (
                    s.get('name', ''),
                    s.get('language', '通用'),
                    s.get('description', '')
                )
            )
            item.setData(Qt.UserRole, s)
            self.list_widget.addItem(item)

    def _on_install(self, item=None):
        if item is None:
            item = self.list_widget.currentItem()
        if not item:
            QMessageBox.information(self, "提示", "请先选中一个片段")
            return

        snippet = item.data(Qt.UserRole)
        if not snippet:
            return

        # 内置片段直接安装
        if 'body' in snippet:
            try:
                from core.snippets import Snippet, get_snippet_manager
                mgr = get_snippet_manager()
                s = Snippet(
                    name=snippet.get('name', ''),
                    prefix=((snippet.get('name') or '').strip().split() or ['snippet'])[0].lower(),
                    body=snippet.get('body', ''),
                    description=snippet.get('description', ''),
                    scope=snippet.get('language', ''),
                )
                mgr.add(s)
                QMessageBox.information(
                    self, "成功",
                    "已安装片段: " + s.name
                )
            except Exception as e:
                QMessageBox.warning(self, "失败", str(e))
        else:
            self.client.download_async(snippet)

    def _on_download_done(self, prefix):
        QMessageBox.information(self, "成功", "已安装: " + prefix)

    def _on_download_failed(self, err):
        QMessageBox.warning(self, "失败", err)