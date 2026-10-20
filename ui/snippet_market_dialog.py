# -*- coding: utf-8 -*-
"""代码片段库对话框（本地）

## 从"市场"改为"本地库"

原文件是「代码片段市场」，依赖 `core.snippet_market.SnippetMarketClient`
去拉取一个**不存在的 GitHub 仓库**（实测 HTTP 404）。现改为读取**本地
片段包目录**（默认 `<应用根>/data/snippet_packs`，可自选目录）：

* 目录里的每个 `.json` 文件就是一个片段包（格式见 `core/snippet_market.py`）；
* 「导入选中」把片段登记进本地片段管理器（`core/snippets.SnippetManager`）；
* 目录为空时展示**内置示例**，让用户知道片段包长什么样。

## 保留的 UI

语言筛选 / 关键词搜索 / 双击导入 —— 这些交互与"内容来自哪里"无关，
直接复用，不重写。
"""
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.snippet_market import SnippetLibrary


class SnippetMarketDialog(QDialog):
    """代码片段库（本地片段包）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("代码片段库")
        self.resize(760, 520)

        self.client = SnippetLibrary(
            self, source_dir=SnippetLibrary.saved_source_dir()
        )
        self.client.fetch_completed.connect(self._on_fetch_done)
        self.client.fetch_failed.connect(self._on_fetch_failed)
        self.client.download_completed.connect(self._on_download_done)
        self.client.download_failed.connect(self._on_download_failed)

        self._snippets = []

        self._build_ui()
        self._apply_style()

        # 自动加载
        self.client.fetch_async()

    # ---------- UI ----------
    def _build_ui(self):
        layout = QVBoxLayout(self)

        # 目录行
        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("片段包目录:"))
        self.dir_label = QLabel(self.client.source_dir)
        self.dir_label.setStyleSheet("color: #888;")
        self.dir_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        dir_row.addWidget(self.dir_label, 1)

        choose_btn = QPushButton("📂 选择目录…")
        choose_btn.setToolTip("选择一个包含 .json 片段包的目录")
        choose_btn.clicked.connect(self._on_choose_dir)
        dir_row.addWidget(choose_btn)
        layout.addLayout(dir_row)

        # 过滤行
        top = QHBoxLayout()

        top.addWidget(QLabel("语言:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems([
            "全部", "Python", "JavaScript", "TypeScript",
            "SQL", "HTML", "CSS", "Shell",
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

        install_btn = QPushButton("⬇ 导入选中")
        install_btn.setToolTip("把选中片段加入本地片段库（可在编辑器中用前缀展开）")
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

    # ---------- 目录 ----------
    def _on_choose_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "选择片段包目录", self.client.source_dir
        )
        if not path:
            return
        if not self.client.set_source_dir(path):
            QMessageBox.warning(self, "失败", "无法使用该目录: %s" % path)
            return
        self.dir_label.setText(self.client.source_dir)
        self.client.fetch_async(force=True)

    # ---------- 数据 ----------
    def _on_fetch_done(self, snippets):
        builtin = []
        if not snippets:
            # 目录为空 → 展示内置示例，让用户知道片段包格式
            builtin = SnippetLibrary.builtin_snippets()
            for s in builtin:
                s["_builtin"] = True
        self._snippets = list(snippets) + builtin
        self._apply_filter()
        if snippets:
            self.status_label.setText(
                "共 %d 个片段（来自 %s）"
                % (len(snippets), self.client.source_dir)
            )
        else:
            self.status_label.setText(
                "目录中没有片段包，下面是**内置示例**（可导入试用手感）。\n"
                "片段包目录：%s" % self.client.source_dir
            )

    def _on_fetch_failed(self, err):
        self.status_label.setText("读取失败: " + err)

    def _apply_filter(self):
        """应用语言/关键词过滤"""
        lang = self.lang_combo.currentText().lower()
        keyword = self.search_edit.text().strip().lower()

        self.list_widget.clear()

        for s in self._snippets:
            s_lang = (s.get('language') or '').lower()
            s_name = (s.get('name') or '').lower()
            s_desc = (s.get('description') or '').lower()

            if lang != "全部" and lang not in s_lang:
                continue
            if keyword and (keyword not in s_name
                            and keyword not in s_desc):
                continue

            tag = "内置" if s.get("_builtin") else "本地"
            item = QListWidgetItem(
                "📌 %s  [%s · %s]\n    %s" % (
                    s.get('name', ''),
                    s.get('language', '通用'),
                    tag,
                    s.get('description', ''),
                )
            )
            item.setData(Qt.UserRole, s)
            self.list_widget.addItem(item)

    # ---------- 导入 ----------
    def _on_install(self, item=None):
        if item is None:
            item = self.list_widget.currentItem()
        if not item:
            QMessageBox.information(self, "提示", "请先选中一个片段")
            return

        snippet = item.data(Qt.UserRole)
        if not snippet:
            return
        if not snippet.get("body"):
            QMessageBox.warning(self, "失败", "该片段没有正文（body 为空）")
            return

        # 统一走本地安装（内置示例也走同一条路，不再分支）
        self.client.download_async(snippet)

    def _on_download_done(self, prefix):
        QMessageBox.information(
            self, "已导入",
            "片段已加入本地片段库。\n\n"
            "在编辑器中输入前缀「%s」后触发补全即可展开。" % prefix
        )

    def _on_download_failed(self, err):
        QMessageBox.warning(self, "导入失败", err)


# 向后兼容别名
SnippetLibraryDialog = SnippetMarketDialog


def show_snippet_library(parent=None):
    """便捷入口"""
    dlg = SnippetMarketDialog(parent)
    dlg.exec_()
