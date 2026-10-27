# -*- coding: utf-8 -*-
"""TODO 面板插件"""
import os
import re

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.plugins import PluginBase


TODO_PATTERN = re.compile(
    r'(#|//|/\*|\*)\s*(TODO|FIXME|XXX|HACK|NOTE)[:\s]*(.*)',
    re.IGNORECASE
)


class TodoPanel(QDockWidget):
    """TODO 面板"""

    def __init__(self, api, main_window, parent=None):
        super().__init__("TODO", parent or main_window)
        self.setObjectName("TodoPanel")
        self.api = api
        self.main_window = main_window

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 工具栏
        toolbar = QHBoxLayout()

        self.scan_file_btn = QPushButton("📄 扫描当前")
        self.scan_file_btn.clicked.connect(self.scan_current_file)
        toolbar.addWidget(self.scan_file_btn)

        self.scan_folder_btn = QPushButton("📁 扫描文件夹")
        self.scan_folder_btn.clicked.connect(self.scan_folder)
        toolbar.addWidget(self.scan_folder_btn)

        toolbar.addStretch()

        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #888;")
        toolbar.addWidget(self.count_label)

        layout.addLayout(toolbar)

        # 搜索过滤
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("过滤:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("关键词...")
        self.filter_edit.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.filter_edit)
        layout.addLayout(filter_row)

        # 树
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["类型", "描述", "文件", "行"])
        self.tree.setColumnWidth(0, 80)
        self.tree.setColumnWidth(1, 400)
        self.tree.itemDoubleClicked.connect(self._on_jump)
        layout.addWidget(self.tree)

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
            }
            QTreeWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                font-size: 12px;
            }
            QTreeWidget::item { padding: 3px; }
            QTreeWidget::item:selected { background-color: #094771; }
            QHeaderView::section {
                background-color: #252526;
                color: #888;
                border: none;
                padding: 4px;
            }
            QLineEdit {
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
                padding: 4px 8px;
            }
            QPushButton:hover { background-color: #1177bb; }
        """)

    def scan_current_file(self):
        """扫描当前文件"""
        try:
            if self.api is None:
                return
            text = self.api.get_current_text()
            filepath = self.api.get_current_filepath() or ""

            items = self._scan_text(text, filepath)
            self._add_items(items)
        except Exception as e:
            print(f"[Todo] 扫描失败: {e}")

    def scan_folder(self):
        """扫描文件夹"""
        folder = QFileDialog.getExistingDirectory(
            self, "选择文件夹"
        )
        if not folder:
            return

        self.tree.clear()
        count = 0

        for root, dirs, files in os.walk(folder):
            # 跳过目录
            dirs[:] = [d for d in dirs if d not in (
                '.git', '__pycache__', 'node_modules', 'venv'
            )]

            for fname in files:
                if not fname.endswith((
                    '.py', '.pyw', '.js', '.ts', '.c', '.cpp',
                    '.h', '.hpp', '.java', '.go', '.rs', '.md'
                )):
                    continue

                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, encoding='utf-8',
                              errors='replace') as f:
                        text = f.read()
                    items = self._scan_text(text, fpath)
                    self._add_items(items)
                    count += len(items)
                except Exception:
                    pass

        self.count_label.setText(f"共 {count} 项")

    def _scan_text(self, text, filepath):
        """扫描文本（应用插件设置 max_items）"""
        items = []
        try:
            limit = int(self.api.get_config("max_items", 200))
        except Exception:
            limit = 200
        for i, line in enumerate(text.splitlines(), 1):
            if len(items) >= limit:
                break
            m = TODO_PATTERN.search(line)
            if m:
                items.append({
                    'type': m.group(2).upper(),
                    'desc': m.group(3).strip() or "(无描述)",
                    'filepath': filepath,
                    'line': i,
                })
        return items

    def _add_items(self, items):
        """添加项"""
        for item in items:
            tree_item = QTreeWidgetItem(self.tree)
            tree_item.setText(0, item['type'])

            # 颜色
            color = {
                'TODO': '#f0ad4e',
                'FIXME': '#f14c4c',
                'XXX': '#f14c4c',
                'HACK': '#f0ad4e',
                'NOTE': '#4dabf7',
            }.get(item['type'], '#d4d4d4')
            tree_item.setForeground(0, QColor(color))

            tree_item.setText(1, item['desc'])
            tree_item.setText(
                2, os.path.basename(item['filepath'])
            )
            tree_item.setText(3, str(item['line']))

            tree_item.setData(0, Qt.UserRole, item)

        self.count_label.setText(
            f"共 {self.tree.topLevelItemCount()} 项"
        )

    def _apply_filter(self):
        """过滤"""
        keyword = self.filter_edit.text().strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            visible = not keyword or keyword in (
                item.text(0) + item.text(1) + item.text(2)
            ).lower()
            item.setHidden(not visible)

    def _on_jump(self, item, column):
        """跳转"""
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        try:
            self.main_window.tabs.open_file(
                data['filepath'], line=data['line'] - 1
            )
        except Exception:
            pass


class Plugin(PluginBase):
    NAME = "todo_panel"
    VERSION = "1.0.0"
    DESCRIPTION = "TODO 面板"
    AUTHOR = "TomJerry"

    def on_activate(self):
        self.api.log("TODO 面板插件已激活")
        # D3 修复：懒创建面板，避免反复启停堆叠 dock
        self._panel = None

        # C4: 避开主窗口的 Ctrl+Shift+T（恢复标签）
        self.api.add_menu(
            "视图/TODO 面板",
            self.show_panel,
            shortcut="Ctrl+Alt+T"
        )

        # ---- v2.4 扩展点 ----
        # 1) 设置 schema：「工具 → 插件设置」
        self.api.register_settings_schema([
            {"key": "max_items", "label": "最多扫描条数",
             "type": "int", "default": 200, "min": 10, "max": 2000},
            {"key": "show_status", "label": "状态栏显示 TODO 计数",
             "type": "bool", "default": True},
        ])
        # 2) 状态栏常驻项（显示 TODO 总数）
        self._status_label = None
        try:
            if bool(self.api.get_config("show_status", True)):
                self._status_label = self.api.add_status_item("TODO: 0")
        except Exception:
            self._status_label = None

    def _update_status_label(self, total):
        """扫描后更新状态栏 TODO 计数"""
        if self._status_label is None:
            return
        try:
            self._status_label.setText("TODO: %d" % total)
        except Exception:
            pass

    def on_deactivate(self):
        # D3: 显式销毁而非只 close
        if self._panel is not None:
            try:
                self.api._host_window().removeDockWidget(self._panel)
            except Exception:
                pass
            self._panel.deleteLater()
            self._panel = None

    def _ensure_panel(self):
        """懒创建面板；首次显示时才实例化并加 dock"""
        if self._panel is None:
            self._panel = TodoPanel(self.api, self.api._host_window())
            self.api._host_window().addDockWidget(
                Qt.BottomDockWidgetArea, self._panel
            )

    def show_panel(self):
        self._ensure_panel()
        self._panel.setVisible(True)
        self._panel.raise_()