#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为全局搜索面板模块，包含：
- GlobalSearchPanel：全局搜索面板（QDockWidget）
- SearchOptionsWidget：搜索选项控件
- SearchResultTree：搜索结果树
- FileResultWidget：单文件结果条目
- 正则/全词/大小写/转义选项
- 文件类型过滤
- 排除目录过滤
- 搜索进度显示
- 搜索结果高亮
- 双击跳转
- 批量替换
- 结果导出
- 搜索历史
- 搜索取消
- 键盘导航
"""

import json
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QMimeData, QPoint, QSettings, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStyle,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.event_bus import StatusMessageEvent, bus
from core.search import (
    FileSearcher,
    SearchMatch,
    SearchOptions,
    SearchResult,
    SearchStatistics,
    build_search_options,
)


# ============================================================
# 常量
# ============================================================
# 面板默认尺寸
DEFAULT_WIDTH = 700
DEFAULT_HEIGHT = 400

# 搜索历史最大条目
MAX_HISTORY_ITEMS = 20

# 预览上下文长度
PREVIEW_CONTEXT_LENGTH = 100

# 结果树列宽
COL_FILE_WIDTH = 300
COL_LINE_WIDTH = 60
COL_MATCH_WIDTH = 300

# 常用文件过滤预设
FILE_FILTER_PRESETS = [
    ("所有文件", "*.*"),
    ("Python", "*.py"),
    ("JavaScript/TypeScript", "*.js;*.jsx;*.ts;*.tsx"),
    ("C/C++", "*.c;*.cpp;*.cc;*.cxx;*.h;*.hpp"),
    ("Java", "*.java"),
    ("Go", "*.go"),
    ("Rust", "*.rs"),
    ("Web 前端", "*.html;*.htm;*.css;*.scss;*.less"),
    ("数据文件", "*.json;*.xml;*.yaml;*.yml;*.toml;*.ini;*.csv"),
    ("文档", "*.md;*.rst;*.txt"),
    ("日志", "*.log"),
    ("配置文件", "*.conf;*.cfg;*.config;*.properties"),
]

# 排除目录预设
EXCLUDE_DIRS_PRESETS = [
    ".git", ".svn", ".hg",
    "__pycache__", "node_modules",
    ".venv", "venv", "env",
    ".idea", ".vscode",
    "build", "dist", "target",
]


# ============================================================
# 结果节点类型
# ============================================================
NODE_TYPE_FILE = 0
NODE_TYPE_MATCH = 1


# ============================================================
# 搜索结果树
# ============================================================
class SearchResultTree(QTreeWidget):
    """
    搜索结果树。

    显示搜索结果，支持:
    - 文件分组
    - 匹配项展开
    - 双击跳转
    - 右键菜单
    """

    # 信号
    match_activated = pyqtSignal(str, int, int, int, int)  # filepath, start, end, line, col
    file_activated = pyqtSignal(str, int)  # filepath, line

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setColumnCount(3)
        self.setHeaderLabels(["文件 / 匹配内容", "行", "列"])
        self.setIndentation(16)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setSortingEnabled(False)

        # 列宽
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)

        # 连接信号
        self.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # 样式
        self._apply_style()

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QTreeWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                font-size: 12px;
                outline: none;
            }
            QTreeWidget::item {
                padding: 3px 4px;
                border-radius: 2px;
            }
            QTreeWidget::item:hover {
                background-color: #2a2d2e;
            }
            QTreeWidget::item:selected {
                background-color: #094771;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #252526;
                color: #cccccc;
                border: none;
                border-bottom: 1px solid #3c3c3c;
                padding: 4px 6px;
                font-weight: bold;
            }
        """)

    def refresh_theme(self, theme):
        """主题变更时刷新样式

        ★ 真实桌面验证发现的缺陷：
            `SearchResultTree` 在 `_apply_style()` 里**写死深色**，
            但它没有 `refresh_theme` 方法，而主题刷新走的是
            `ThemeLoader.notify_widgets()` → 只调用**拥有
            `refresh_theme` 的控件**。于是：编辑器与其它面板都跟着
            主题变成浅色时，**"文件 / 匹配内容"这块结果树仍然是黑的**，
            像一块缺角。

            修复：与其它面板一致的实现 —— 首次保存原始 QSS，
            之后用 `adapt_qss_colors()` 按主题换算。
        """
        try:
            from infrastructure.theme_loader import adapt_qss_colors
            if not getattr(self, '_original_qss', ''):
                self._original_qss = self.styleSheet()
            if self._original_qss:
                self.setStyleSheet(
                    adapt_qss_colors(self._original_qss, theme)
                )
        except Exception as e:
            print(f"[SearchResultTree] refresh_theme 失败: {e}")

    # --------------------------------------------------------
    # 添加结果
    # --------------------------------------------------------
    def add_file_result(self, filepath: str,
                         matches: List[SearchMatch]) -> QTreeWidgetItem:
        """
        添加文件结果。

        参数:
            filepath: 文件路径
            matches: 匹配列表

        返回:
            文件节点
        """
        # 文件节点
        file_item = QTreeWidgetItem(self)
        file_item.setData(0, Qt.UserRole + 1, NODE_TYPE_FILE)
        file_item.setData(0, Qt.UserRole + 2, filepath)

        # 显示相对路径（如果可能）
        display_name = os.path.basename(filepath)
        display_dir = os.path.dirname(filepath)

        if display_dir:
            display = f"{display_name}  —  {display_dir}"
        else:
            display = display_name

        file_item.setText(0, f"📄 {display}")
        file_item.setText(1, f"{len(matches)} 项")
        file_item.setToolTip(0, filepath)

        # 字体加粗
        font = file_item.font(0)
        font.setBold(True)
        file_item.setFont(0, font)

        # 添加匹配项
        for match in matches:
            match_item = QTreeWidgetItem(file_item)
            match_item.setData(0, Qt.UserRole + 1, NODE_TYPE_MATCH)
            match_item.setData(0, Qt.UserRole + 2, filepath)
            match_item.setData(0, Qt.UserRole + 3, match.start)
            match_item.setData(0, Qt.UserRole + 4, match.end)
            match_item.setData(0, Qt.UserRole + 5, match.line)
            match_item.setData(0, Qt.UserRole + 6, match.col)

            # 显示行内容（带高亮）
            line_text = match.line_text.strip()
            if len(line_text) > PREVIEW_CONTEXT_LENGTH:
                # 定位到匹配位置附近
                match_in_line = match.text
                if match_in_line and match_in_line in line_text:
                    idx = line_text.find(match_in_line)
                    start = max(0, idx - 30)
                    end = min(len(line_text), idx + len(match_in_line) + 30)
                    prefix = "..." if start > 0 else ""
                    suffix = "..." if end < len(line_text) else ""
                    line_text = prefix + line_text[start:end] + suffix

            match_item.setText(0, line_text)
            match_item.setText(1, str(match.line))
            match_item.setText(2, str(match.col))

            # 匹配文本加粗
            font = match_item.font(0)
            font.setBold(False)
            match_item.setFont(0, font)

            # 设置颜色
            match_item.setForeground(0, QBrush(QColor("#cccccc")))

        # 默认展开文件节点
        file_item.setExpanded(True)

        return file_item

    def add_file_result_batch(self, filepath: str,
                                matches: List[SearchMatch]):
        """批量添加（性能优化，禁用更新）"""
        self.setUpdatesEnabled(False)
        try:
            self.add_file_result(filepath, matches)
        finally:
            self.setUpdatesEnabled(True)

    # --------------------------------------------------------
    # 清空
    # --------------------------------------------------------
    def clear_results(self):
        """清空所有结果"""
        self.clear()

    def get_file_count(self) -> int:
        """获取文件数量"""
        count = 0
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.data(0, Qt.UserRole + 1) == NODE_TYPE_FILE:
                count += 1
        return count

    def get_match_count(self) -> int:
        """获取匹配总数"""
        count = 0
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            for j in range(item.childCount()):
                count += 1
        return count

    def get_all_results(self) -> Dict[str, List[SearchMatch]]:
        """获取所有结果（文件路径 -> 匹配列表）"""
        results = {}

        for i in range(self.topLevelItemCount()):
            file_item = self.topLevelItem(i)
            filepath = file_item.data(0, Qt.UserRole + 2)
            if not filepath:
                continue

            matches = []
            for j in range(file_item.childCount()):
                match_item = file_item.child(j)
                try:
                    match = SearchMatch(
                        start=match_item.data(0, Qt.UserRole + 3),
                        end=match_item.data(0, Qt.UserRole + 4),
                        line=match_item.data(0, Qt.UserRole + 5),
                        col=match_item.data(0, Qt.UserRole + 6),
                        text="",
                        line_text=match_item.text(0),
                    )
                    matches.append(match)
                except Exception:
                    continue

            results[filepath] = matches

        return results

    # --------------------------------------------------------
    # 双击跳转
    # --------------------------------------------------------
    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """双击项"""
        node_type = item.data(0, Qt.UserRole + 1)

        if node_type == NODE_TYPE_MATCH:
            # 匹配项：跳转到具体位置
            filepath = item.data(0, Qt.UserRole + 2)
            start = item.data(0, Qt.UserRole + 3)
            end = item.data(0, Qt.UserRole + 4)
            line = item.data(0, Qt.UserRole + 5)
            col = item.data(0, Qt.UserRole + 6)

            if filepath:
                self.match_activated.emit(filepath, start, end, line, col)

        elif node_type == NODE_TYPE_FILE:
            # 文件节点：跳转到第一行
            filepath = item.data(0, Qt.UserRole + 2)
            if filepath:
                line = 0
                if item.childCount() > 0:
                    line = item.child(0).data(0, Qt.UserRole + 5)
                self.file_activated.emit(filepath, line)

    # --------------------------------------------------------
    # 右键菜单
    # --------------------------------------------------------
    def _show_context_menu(self, pos):
        """显示右键菜单"""
        item = self.itemAt(pos)
        if item is None:
            return

        menu = QMenu(self)
        node_type = item.data(0, Qt.UserRole + 1)

        if node_type == NODE_TYPE_MATCH:
            filepath = item.data(0, Qt.UserRole + 2)

            # 打开
            open_act = menu.addAction("📂 打开")
            open_act.triggered.connect(
                lambda: self._on_item_double_clicked(item, 0)
            )

            menu.addSeparator()

            # 复制
            copy_line_act = menu.addAction("📋 复制此行内容")
            copy_line_act.triggered.connect(
                lambda: self._copy_to_clipboard(item.text(0))
            )

            if filepath:
                copy_path_act = menu.addAction("📋 复制文件路径")
                copy_path_act.triggered.connect(
                    lambda: self._copy_to_clipboard(filepath)
                )

                menu.addSeparator()

                # 在文件管理器中显示
                reveal_act = menu.addAction("📁 在文件管理器中显示")
                reveal_act.triggered.connect(
                    lambda: self._reveal_in_explorer(filepath)
                )

        elif node_type == NODE_TYPE_FILE:
            filepath = item.data(0, Qt.UserRole + 2)

            # 展开/折叠
            if item.isExpanded():
                collapse_act = menu.addAction("⊟ 折叠")
                collapse_act.triggered.connect(lambda: item.setExpanded(False))
            else:
                expand_act = menu.addAction("⊞ 展开")
                expand_act.triggered.connect(lambda: item.setExpanded(True))

            menu.addSeparator()

            # 复制路径
            if filepath:
                copy_path_act = menu.addAction("📋 复制文件路径")
                copy_path_act.triggered.connect(
                    lambda: self._copy_to_clipboard(filepath)
                )

                reveal_act = menu.addAction("📁 在文件管理器中显示")
                reveal_act.triggered.connect(
                    lambda: self._reveal_in_explorer(filepath)
                )

        menu.addSeparator()

        # 全部展开/折叠
        expand_all_act = menu.addAction("⊞ 全部展开")
        expand_all_act.triggered.connect(self.expandAll)

        collapse_all_act = menu.addAction("⊟ 全部折叠")
        collapse_all_act.triggered.connect(self.collapseAll)

        menu.addSeparator()

        # 清空
        clear_act = menu.addAction("🗑 清空结果")
        clear_act.triggered.connect(self.clear_results)

        menu.exec(self.viewport().mapToGlobal(pos))

    def _copy_to_clipboard(self, text: str):
        """复制到剪贴板"""
        try:
            QApplication.clipboard().setText(text)
        except Exception:
            pass

    def _reveal_in_explorer(self, filepath: str):
        """在文件管理器中显示"""
        import subprocess

        try:
            if sys.platform == 'win32':
                # P1-B1: /select, 必须作为单个参数
                subprocess.Popen(
                    ['explorer',
                     f'/select,{filepath.replace("/", chr(92))}']
                )
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', '-R', filepath])
            else:
                folder = os.path.dirname(filepath)
                subprocess.Popen(['xdg-open', folder])
        except Exception as e:
            print(f"[SearchResultTree] 打开失败: {e}")


# ============================================================
# 全局搜索面板
# ============================================================
class GlobalSearchPanel(QDockWidget):
    """
    全局搜索面板。

    功能:
    - 在多文件中搜索（Ctrl+Shift+F）
    - 正则表达式支持
    - 大小写敏感/全词匹配/转义
    - 文件类型过滤
    - 排除目录
    - 结果树展示
    - 双击跳转
    - 批量替换
    - 结果导出
    - 搜索历史
    - 搜索进度
    - 搜索取消

    信号:
        search_started(str): 搜索开始
        search_finished(SearchResult): 搜索完成
        match_activated(str, int, int, int, int): 匹配激活（路径, start, end, 行, 列）
        file_activated(str, int): 文件激活（路径, 行）
        replace_requested(str, str, dict, object): 请求替换
            （模式, 替换文本, 结果, SearchOptions）

    注意（P0-3）:
        `replace_requested` 的第 4 个参数是 **SearchOptions 对象**。
        缺陷背景：原先只传 (模式, 替换文本, 结果)，接收方
        `MainWindow._on_global_replace` 只能重建
        `SearchOptions(pattern=...)`（即全默认值）—— 面板上的
        "正则 / 大小写 / 全词 / 转义 / 多行"勾选被**静默丢弃**，
        正则搜索之后按字面量替换。把选项对象随信号带过去，
        才能保证"搜索看到什么，替换就替什么"。
    """

    search_started = pyqtSignal(str)
    search_finished = pyqtSignal(object)
    match_activated = pyqtSignal(str, int, int, int, int)
    file_activated = pyqtSignal(str, int)
    replace_requested = pyqtSignal(str, str, dict, object)

    def __init__(self, main_window, parent=None):
        """
        参数:
            main_window: 主窗口（提供 tabs 等）
            parent: 父控件
        """
        super().__init__("全局搜索", parent or main_window)

        self.main_window = main_window

        # 搜索引擎
        self.searcher = FileSearcher()

        # 当前搜索
        self.current_result: Optional[SearchResult] = None
        self._searching: bool = False
        # P0-3: 产生 current_result 的那次搜索所用的选项（替换时复用）
        self.current_options: Optional[SearchOptions] = None

        # 搜索历史
        self._pattern_history: List[str] = []
        self._replace_history: List[str] = []

        # 状态
        self._settings = QSettings("QingCao", "SearchPanel")
        self._load_history()

        # 设置属性
        self.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)
        self.setObjectName("GlobalSearchPanel")

        # 构建 UI
        self._build_ui()

        # 连接信号
        self._connect_signals()

    # ========================================================
    # UI 构建
    # ========================================================
    def _build_ui(self):
        """构建 UI"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # ========== 第 1 行：搜索模式 ==========
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        # 搜索模式标签
        mode_label = QLabel("模式:")
        mode_label.setFixedWidth(40)
        row1.addWidget(mode_label)

        # 正则表达式复选框
        self.regex_cb = QCheckBox("正则")
        self.regex_cb.setToolTip("使用正则表达式搜索")
        row1.addWidget(self.regex_cb)

        # 大小写敏感
        self.case_cb = QCheckBox("大小写")
        self.case_cb.setToolTip("区分大小写")
        row1.addWidget(self.case_cb)

        # 全词匹配
        self.whole_word_cb = QCheckBox("全词")
        self.whole_word_cb.setToolTip("全词匹配")
        row1.addWidget(self.whole_word_cb)

        # 转义
        self.escape_cb = QCheckBox("转义")
        self.escape_cb.setToolTip("将特殊字符按字面处理")
        row1.addWidget(self.escape_cb)

        # 多行
        self.multiline_cb = QCheckBox("多行")
        self.multiline_cb.setToolTip("多行模式（^ 和 $ 匹配行首行尾）")
        row1.addWidget(self.multiline_cb)

        row1.addStretch()

        # 搜索目录
        self.dir_label = QLabel("目录: 未选择")
        self.dir_label.setStyleSheet("color: #888;")
        row1.addWidget(self.dir_label)

        self.browse_dir_btn = QPushButton("📁")
        self.browse_dir_btn.setFixedSize(28, 24)
        self.browse_dir_btn.setToolTip("选择搜索目录")
        self.browse_dir_btn.clicked.connect(self._browse_directory)
        row1.addWidget(self.browse_dir_btn)

        layout.addLayout(row1)

        # ========== 第 2 行：搜索框 ==========
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        self.pattern_edit = QLineEdit()
        self.pattern_edit.setPlaceholderText("搜索内容...")
        self.pattern_edit.setClearButtonEnabled(True)
        self.pattern_edit.returnPressed.connect(self._start_search)
        row2.addWidget(self.pattern_edit, 3)

        self.replace_edit = QLineEdit()
        self.replace_edit.setPlaceholderText("替换为...")
        row2.addWidget(self.replace_edit, 2)

        self.search_btn = QPushButton("🔍 搜索")
        self.search_btn.setFixedWidth(80)
        self.search_btn.clicked.connect(self._start_search)
        row2.addWidget(self.search_btn)

        self.cancel_btn = QPushButton("✖ 取消")
        self.cancel_btn.setFixedWidth(60)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_search)
        row2.addWidget(self.cancel_btn)

        layout.addLayout(row2)

        # ========== 第 3 行：文件过滤 ==========
        row3 = QHBoxLayout()
        row3.setSpacing(6)

        filter_label = QLabel("文件:")
        filter_label.setFixedWidth(40)
        row3.addWidget(filter_label)

        self.filter_combo = QComboBox()
        self.filter_combo.setEditable(True)
        self.filter_combo.setMinimumWidth(180)

        for name, pattern in FILE_FILTER_PRESETS:
            self.filter_combo.addItem(name, pattern)

        self.filter_combo.setCurrentIndex(0)
        self.filter_combo.setToolTip("文件类型过滤，如 *.py;*.txt")
        row3.addWidget(self.filter_combo)

        # 排除目录
        exclude_label = QLabel("排除:")
        exclude_label.setFixedWidth(40)
        row3.addWidget(exclude_label)

        self.exclude_edit = QLineEdit()
        self.exclude_edit.setPlaceholderText(".git;node_modules;build")
        self.exclude_edit.setText(";".join(EXCLUDE_DIRS_PRESETS[:8]))
        self.exclude_edit.setToolTip("排除的目录，用分号分隔")
        row3.addWidget(self.exclude_edit, 1)

        # 包含隐藏文件
        self.hidden_cb = QCheckBox("包含隐藏")
        row3.addWidget(self.hidden_cb)

        row3.addStretch()

        # 结果统计
        self.result_label = QLabel("")
        self.result_label.setStyleSheet("color: #7ec850; font-weight: bold;")
        row3.addWidget(self.result_label)

        layout.addLayout(row3)

        # ========== 进度条 ==========
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # ========== 结果树 ==========
        self.result_tree = SearchResultTree()
        layout.addWidget(self.result_tree, 1)

        # ========== 底部操作按钮 ==========
        row4 = QHBoxLayout()
        row4.setSpacing(6)

        self.replace_all_btn = QPushButton("🔄 全部替换")
        self.replace_all_btn.setEnabled(False)
        self.replace_all_btn.clicked.connect(self._replace_all)
        row4.addWidget(self.replace_all_btn)

        self.export_btn = QPushButton("📤 导出结果")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export_results)
        row4.addWidget(self.export_btn)

        row4.addStretch()

        self.clear_btn = QPushButton("🗑 清空")
        self.clear_btn.clicked.connect(self._clear_results)
        row4.addWidget(self.clear_btn)

        self.close_btn = QPushButton("✖ 关闭")
        self.close_btn.clicked.connect(self.hide)
        row4.addWidget(self.close_btn)

        layout.addLayout(row4)

        self.setWidget(container)

        # 应用样式
        self._apply_style()

    def refresh_theme(self, theme):
        """主题变更时刷新样式（v3.0）"""
        try:
            from infrastructure.theme_loader import adapt_qss_colors
            if not hasattr(self, '_original_qss') or not self._original_qss:
                self._original_qss = self.styleSheet()
            if self._original_qss:
                qss = adapt_qss_colors(self._original_qss, theme)
                self.setStyleSheet(qss)
        except Exception as e:
            print(f"[{self.__class__.__name__}] refresh_theme 失败: {e}")

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QDockWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-size: 12px;
            }
            QDockWidget::title {
                background-color: #252526;
                padding: 4px 8px;
                border-bottom: 1px solid #3c3c3c;
            }
            QLineEdit {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #007acc;
            }
            QComboBox {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 12px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                color: #d4d4d4;
                selection-background-color: #094771;
                border: 1px solid #3c3c3c;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 4px 10px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0a4d7a;
            }
            QPushButton:disabled {
                background-color: #3c3c3c;
                color: #666;
            }
            QCheckBox {
                color: #d4d4d4;
                font-size: 12px;
                spacing: 4px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #555;
                border-radius: 2px;
                background-color: #3c3c3c;
            }
            QCheckBox::indicator:checked {
                background-color: #007acc;
                border-color: #007acc;
            }
            QProgressBar {
                background-color: #2d2d2d;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #007acc;
                border-radius: 2px;
            }
        """)

    def _connect_signals(self):
        """连接内部信号"""
        # 结果树信号
        self.result_tree.match_activated.connect(self._on_match_activated)
        self.result_tree.file_activated.connect(self._on_file_activated)

        # 搜索引擎信号
        self.searcher.search_started.connect(self._on_search_started)
        self.searcher.file_result.connect(self._on_file_result)
        self.searcher.search_progress.connect(self._on_search_progress)
        self.searcher.search_finished.connect(self._on_search_finished)
        self.searcher.search_error.connect(self._on_search_error)

    # ========================================================
    # 目录选择
    # ========================================================
    def _browse_directory(self):
        """浏览目录"""
        current = self._get_search_directory()
        directory = QFileDialog.getExistingDirectory(
            self, "选择搜索目录", current
        )

        if directory:
            self._search_directory = directory
            self.dir_label.setText(f"目录: {directory}")
            self.dir_label.setToolTip(directory)

    def _get_search_directory(self) -> str:
        """获取搜索目录"""
        # 优先使用用户选择的目录
        if hasattr(self, '_search_directory') and self._search_directory:
            return self._search_directory

        # 尝试从主窗口获取当前项目
        if self.main_window:
            if hasattr(self.main_window, 'current_project'):
                project = self.main_window.current_project
                if project and hasattr(project, 'root_path'):
                    return project.root_path

            # 尝试从目录树获取
            if hasattr(self.main_window, 'dir_tree'):
                root = self.main_window.dir_tree.get_root()
                if root:
                    return root

            # 尝试从当前文件获取
            if hasattr(self.main_window, 'tabs'):
                proxy = self.main_window.tabs.current_proxy()
                if proxy and proxy.document and proxy.document.filepath:
                    return os.path.dirname(proxy.document.filepath)

        return os.getcwd()

    # ========================================================
    # 搜索
    # ========================================================
    def build_options(self) -> SearchOptions:
        """按面板当前勾选构造 SearchOptions（P0-3：选项的**唯一构造点**）

        缺陷背景（P0-3，实测确认）:
            本面板原先在 `_start_search()` 里就地拼一份带
            is_regex/case_sensitive/whole_word/escape_pattern/multi_line
            的选项，而"全部替换"只发 (pattern, 替换文本, 结果) 三个值；
            接收方只能重建 `SearchOptions(pattern=...)`，其余全是默认值。
            ——即"面板勾了正则，替换却按字面量"。

        现在搜索与替换共用本方法（替换端还把结果随信号带走），
        从结构上杜绝"同一个概念在两处各自定义"。

        说明：这里仍然用 dataclass 的默认性能参数（threads/hyperscan/
        timeout），与修复前 `_start_search` 的行为完全一致；
        不顺手改成 `from_preferences()`，避免把 P0-3 的修复
        和其他行为的变更混在一起。
        """
        return SearchOptions(
            pattern=self.pattern_edit.text(),
            is_regex=self.regex_cb.isChecked(),
            case_sensitive=self.case_cb.isChecked(),
            whole_word=self.whole_word_cb.isChecked(),
            escape_pattern=self.escape_cb.isChecked(),
            multi_line=self.multiline_cb.isChecked(),
        )

    def _start_search(self):
        """开始搜索"""
        if self._searching:
            return

        pattern = self.pattern_edit.text()
        if not pattern:
            return

        # 添加搜索历史
        self._add_pattern_history(pattern)

        # 构建搜索选项（P0-3：唯一构造点）
        options = self.build_options()
        # 记下"产生当前结果的那次搜索"用的选项：
        # 用户完全可能在搜索之后才改勾选，替换时必须复用**这次**的选项，
        # 否则会按新选项去替换旧结果（匹配集根本不是同一批）。
        self.current_options = options

        # 获取搜索目录
        search_dir = self._get_search_directory()
        if not search_dir or not os.path.isdir(search_dir):
            self._show_message("搜索目录无效", "warning")
            return

        # 获取文件过滤
        file_filter = self.filter_combo.currentData()
        if not file_filter:
            file_filter = self.filter_combo.currentText()
            # 如果当前文本是预设名称，取其模式
            for name, pattern_text in FILE_FILTER_PRESETS:
                if name == file_filter:
                    file_filter = pattern_text
                    break

        # 获取排除目录
        exclude_text = self.exclude_edit.text()
        exclude_dirs = [
            d.strip() for d in exclude_text.split(';') if d.strip()
        ]

        # 是否包含隐藏
        include_hidden = self.hidden_cb.isChecked()

        # 清空结果
        self.result_tree.clear_results()
        self.current_result = None

        # 更新 UI
        self.search_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.replace_all_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.result_label.setText("搜索中...")
        self.result_label.setStyleSheet("color: #f0ad4e; font-weight: bold;")
        self._searching = True

        # 发射信号
        self.search_started.emit(pattern)

        # 开始搜索
        self.searcher.search(
            search_dir, options,
            file_filter=file_filter,
            exclude_dirs=exclude_dirs,
            include_hidden=include_hidden,
        )

    def _cancel_search(self):
        """取消搜索"""
        if not self._searching:
            return

        self.searcher.cancel()
        self.result_label.setText("已取消")
        self.result_label.setStyleSheet("color: #f0ad4e;")

    def _on_search_started(self, pattern: str, file_count: int):
        """搜索开始回调"""
        self.progress_bar.setRange(0, file_count)
        self.progress_bar.setValue(0)
        self.result_label.setText(f"搜索中... (0/{file_count})")

    def _on_file_result(self, filepath: str, matches: List[SearchMatch]):
        """单文件结果回调"""
        try:
            self.result_tree.add_file_result_batch(filepath, matches)
        except Exception as e:
            print(f"[GlobalSearchPanel] 添加结果失败: {e}")

    def _on_search_progress(self, current: int, total: int):
        """搜索进度回调"""
        self.progress_bar.setValue(current)
        self.result_label.setText(f"搜索中... ({current}/{total})")

    def _on_search_finished(self, result: SearchResult):
        """搜索完成回调"""
        self._searching = False
        self.current_result = result

        self.search_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)

        # 更新结果统计
        file_count = result.get_file_count()
        match_count = result.count

        if result.error:
            self.result_label.setText(f"搜索错误: {result.error}")
            self.result_label.setStyleSheet("color: #f14c4c; font-weight: bold;")
        elif result.cancelled:
            self.result_label.setText(
                f"已取消 ({file_count} 文件, {match_count} 项)"
            )
            self.result_label.setStyleSheet("color: #f0ad4e; font-weight: bold;")
        else:
            elapsed = result.elapsed_ms
            if elapsed < 1000:
                time_str = f"{elapsed:.0f}ms"
            else:
                time_str = f"{elapsed/1000:.2f}s"

            self.result_label.setText(
                f"✓ {file_count} 文件, {match_count} 项 ({time_str})"
            )
            self.result_label.setStyleSheet("color: #7ec850; font-weight: bold;")

        # 启用/禁用操作按钮
        has_results = match_count > 0
        self.replace_all_btn.setEnabled(has_results and bool(self.replace_edit.text()))
        self.export_btn.setEnabled(has_results)

        # 发射信号
        self.search_finished.emit(result)

    def _on_search_error(self, error: str):
        """搜索错误回调"""
        self.result_label.setText(f"错误: {error}")
        self.result_label.setStyleSheet("color: #f14c4c; font-weight: bold;")

    # ========================================================
    # 匹配激活与跳转
    # ========================================================
    def _on_match_activated(self, filepath: str, start: int, end: int,
                             line: int, col: int):
        """匹配激活"""
        # 打开文件并跳转
        if self.main_window and hasattr(self.main_window, 'tabs'):
            try:
                proxy = self.main_window.tabs.open_file(filepath)
                if proxy:
                    # 跳转到匹配位置
                    proxy.set_selection(start, end)

                    # 居中显示
                    try:
                        proxy.sc.ensureLineVisible(line - 1)
                    except Exception:
                        pass

                    # 聚焦
                    try:
                        proxy.sc.setFocus()
                    except Exception:
                        pass

            except Exception as e:
                print(f"[GlobalSearchPanel] 打开文件失败: {e}")

        # 发射信号
        self.match_activated.emit(filepath, start, end, line, col)

    def _on_file_activated(self, filepath: str, line: int):
        """文件激活"""
        if self.main_window and hasattr(self.main_window, 'tabs'):
            try:
                proxy = self.main_window.tabs.open_file(filepath)
                if proxy and line > 0:
                    proxy.goto_line(line - 1)
            except Exception as e:
                print(f"[GlobalSearchPanel] 打开文件失败: {e}")

        self.file_activated.emit(filepath, line)

    # ========================================================
    # 替换
    # ========================================================
    def _options_for_replace(self) -> SearchOptions:
        """替换所用的选项（P0-3）

        优先复用"产生当前结果的那次搜索"的选项（`current_options`）：
            结果树里的匹配是按那次选项找出来的，替换必须与之同一套语义。
            若用户在搜索后又改了勾选，用新选项替换旧结果会替换错内容
            （例如"正则 → 字面量"切换后，匹配集完全不是同一批）。
        兜底：没有搜索结果选项时（例如外部直接调用），
            才按面板当前勾选重新构造。
        """
        last = self.current_options
        if last is not None and last.pattern == self.pattern_edit.text():
            return last
        return self.build_options()

    def _replace_all(self):
        """全部替换"""
        if not self.current_result or self.current_result.is_empty:
            self._show_message("没有可替换的结果", "info")
            return

        replace_text = self.replace_edit.text()
        if not replace_text:
            self._show_message("请输入替换内容", "info")
            return

        # 确认对话框
        count = self.current_result.count
        file_count = self.current_result.get_file_count()

        # P0-3: 把"按什么模式替换"写进确认框 ——
        # 修复前这里不显示模式，用户无从发现"我勾了正则却被按字面量替换"。
        replace_options = self._options_for_replace()
        mode_desc = replace_options.describe()

        msg = (f"将在 {file_count} 个文件中替换 {count} 处匹配。\n\n"
               f"搜索模式: {mode_desc}\n"
               f"替换为: {replace_text}\n\n"
               f"此操作无法撤销，是否继续？")

        reply = QMessageBox.question(
            self, "确认替换", msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # 添加历史
        self._add_replace_history(replace_text)

        # 请求替换（由主窗口或编辑器执行）
        #
        # P0-3: 第 4 个参数是本次替换必须遵守的 SearchOptions。
        # 只要它随信号过去，接收方就不需要（也不允许）自己重建默认选项。
        options = replace_options
        self.replace_requested.emit(
            options.pattern or self.pattern_edit.text(),
            replace_text,
            self.current_result.file_results,
            options,
        )

        self._show_message(f"已请求替换 {count} 处", "info")

    # ========================================================
    # 导出结果
    # ========================================================
    def _export_results(self):
        """导出搜索结果"""
        if not self.current_result or self.current_result.is_empty:
            self._show_message("没有可导出的结果", "info")
            return

        filepath, selected_filter = QFileDialog.getSaveFileName(
            self, "导出搜索结果",
            "search_results.txt",
            "文本文件 (*.txt);;JSON 文件 (*.json);;CSV 文件 (*.csv)"
        )

        if not filepath:
            return

        try:
            if filepath.endswith('.json'):
                self._export_json(filepath)
            elif filepath.endswith('.csv'):
                self._export_csv(filepath)
            else:
                self._export_text(filepath)

            self._show_message(f"已导出到 {os.path.basename(filepath)}", "info")

        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _export_text(self, filepath: str):
        """导出为文本"""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("青草编辑器搜索结果\n")
            f.write(f"{'=' * 60}\n")
            f.write(f"搜索模式: {self.pattern_edit.text()}\n")
            f.write(f"文件数: {self.current_result.get_file_count()}\n")
            f.write(f"匹配数: {self.current_result.count}\n")
            f.write(f"耗时: {self.current_result.elapsed_ms:.0f} ms\n")
            f.write(f"{'=' * 60}\n\n")

            for filepath_key, matches in self.current_result.file_results.items():
                f.write(f"\n{filepath_key}\n")
                f.write(f"{'-' * 60}\n")
                for m in matches:
                    f.write(f"  行 {m.line}, 列 {m.col}: {m.line_text.strip()}\n")

    def _export_json(self, filepath: str):
        """导出为 JSON"""
        data = {
            'pattern': self.pattern_edit.text(),
            'file_count': self.current_result.get_file_count(),
            'match_count': self.current_result.count,
            'elapsed_ms': self.current_result.elapsed_ms,
            'results': {},
        }

        for fp, matches in self.current_result.file_results.items():
            data['results'][fp] = [m.to_dict() for m in matches]

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _export_csv(self, filepath: str):
        """导出为 CSV"""
        import csv

        with open(filepath, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['文件', '行', '列', '内容'])

            for fp, matches in self.current_result.file_results.items():
                for m in matches:
                    writer.writerow([fp, m.line, m.col, m.line_text.strip()])

    # ========================================================
    # 清空
    # ========================================================
    def _clear_results(self):
        """清空结果"""
        self.result_tree.clear_results()
        self.current_result = None
        # P0-3: 结果没了，产出它的选项也一并失效
        self.current_options = None
        self.result_label.setText("")
        self.replace_all_btn.setEnabled(False)
        self.export_btn.setEnabled(False)

    def clear(self):
        """清空搜索面板"""
        self.pattern_edit.clear()
        self.replace_edit.clear()
        self._clear_results()

    # ========================================================
    # 搜索历史
    # ========================================================
    def _load_history(self):
        """加载历史"""
        try:
            pattern_history = self._settings.value("pattern_history", [])
            if isinstance(pattern_history, str):
                pattern_history = [pattern_history] if pattern_history else []
            self._pattern_history = list(pattern_history)[:MAX_HISTORY_ITEMS]

            replace_history = self._settings.value("replace_history", [])
            if isinstance(replace_history, str):
                replace_history = [replace_history] if replace_history else []
            self._replace_history = list(replace_history)[:MAX_HISTORY_ITEMS]
        except Exception:
            pass

    def _save_history(self):
        """保存历史"""
        try:
            self._settings.setValue("pattern_history",
                                     self._pattern_history[:MAX_HISTORY_ITEMS])
            self._settings.setValue("replace_history",
                                     self._replace_history[:MAX_HISTORY_ITEMS])
        except Exception:
            pass

    def _add_pattern_history(self, pattern: str):
        """添加搜索历史"""
        if not pattern:
            return

        if pattern in self._pattern_history:
            self._pattern_history.remove(pattern)

        self._pattern_history.insert(0, pattern)
        self._pattern_history = self._pattern_history[:MAX_HISTORY_ITEMS]
        self._save_history()

    def _add_replace_history(self, text: str):
        """添加替换历史"""
        if not text:
            return

        if text in self._replace_history:
            self._replace_history.remove(text)

        self._replace_history.insert(0, text)
        self._replace_history = self._replace_history[:MAX_HISTORY_ITEMS]
        self._save_history()

    def get_pattern_history(self) -> List[str]:
        """获取搜索历史"""
        return list(self._pattern_history)

    def get_replace_history(self) -> List[str]:
        """获取替换历史"""
        return list(self._replace_history)

    # ========================================================
    # 显示
    # ========================================================
    def showEvent(self, event):
        """显示事件"""
        super().showEvent(event)

        # 聚焦搜索框
        QTimer.singleShot(100, self.pattern_edit.setFocus)

        # 设置搜索目录标签
        search_dir = self._get_search_directory()
        if search_dir:
            if len(search_dir) > 60:
                display = "..." + search_dir[-57:]
            else:
                display = search_dir
            self.dir_label.setText(f"目录: {display}")
            self.dir_label.setToolTip(search_dir)

    # ========================================================
    # 辅助
    # ========================================================
    def _show_message(self, message: str, level: str = "info"):
        """显示状态消息"""
        try:
            bus.emit_event(StatusMessageEvent(
                message=message, timeout=3000, level=level
            ))
        except Exception:
            pass

    def set_search_pattern(self, pattern: str):
        """设置搜索模式（用于外部调用）"""
        self.pattern_edit.setText(pattern)

    def get_search_pattern(self) -> str:
        """获取当前搜索模式"""
        return self.pattern_edit.text()

    def set_search_directory(self, directory: str):
        """设置搜索目录"""
        self._search_directory = directory
        if directory:
            self.dir_label.setText(f"目录: {directory}")
            self.dir_label.setToolTip(directory)

    def focus_search(self):
        """聚焦到搜索框"""
        self.pattern_edit.setFocus()
        self.pattern_edit.selectAll()

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        """导出面板信息"""
        lines = ["GlobalSearchPanel", "=" * 60]
        lines.append(f"当前搜索: {self.pattern_edit.text()}")
        lines.append(f"替换内容: {self.replace_edit.text()}")
        lines.append(f"搜索目录: {self._get_search_directory()}")
        lines.append(f"正在搜索: {self._searching}")
        lines.append(f"结果文件数: {self.result_tree.get_file_count()}")
        lines.append(f"结果匹配数: {self.result_tree.get_match_count()}")
        lines.append(f"历史记录: {len(self._pattern_history)} 条")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<GlobalSearchPanel pattern={self.pattern_edit.text()!r} "
                f"searching={self._searching}>")


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import shutil
    import tempfile

    from PyQt5.QtWidgets import QApplication, QMainWindow

    app = QApplication(sys.argv)

    # 创建测试目录
    tmp_dir = tempfile.mkdtemp(prefix="qingcao_gsearch_test_")

    # 创建测试文件
    test_files = {
        "file1.py": "def hello():\n    print('Hello World')\n    return 42\n",
        "file2.py": "class MyClass:\n    def hello(self):\n        pass\n",
        "file3.txt": "This is a test.\nHello again!\nhello there.\n",
        "subdir/file4.py": "hello = 'world'\nprint(hello)\n",
    }

    for rel_path, content in test_files.items():
        full_path = os.path.join(tmp_dir, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)

    # 创建主窗口
    win = QMainWindow()
    win.setWindowTitle("GlobalSearchPanel 测试")
    win.resize(900, 600)
    win.show()

    # 创建搜索面板
    panel = GlobalSearchPanel(win)
    win.addDockWidget(Qt.BottomDockWidgetArea, panel)
    panel.show()

    # 设置搜索目录
    panel.set_search_directory(tmp_dir)

    # 连接信号
    panel.search_started.connect(
        lambda p: print(f"[信号] 搜索开始: {p}")
    )
    panel.search_finished.connect(
        lambda r: print(f"[信号] 搜索完成: {r.get_summary()}")
    )
    panel.match_activated.connect(
        lambda fp, s, e, l, c: print(f"[信号] 匹配激活: {fp}:{l}:{c}")
    )
    panel.file_activated.connect(
        lambda fp, l: print(f"[信号] 文件激活: {fp}:{l}")
    )

    # 设置搜索模式并触发
    def do_search():
        panel.set_search_pattern("hello")
        panel._start_search()

    QTimer.singleShot(1000, do_search)

    # 5 秒后打印信息并退出
    def print_and_quit():
        print()
        print(panel.dump())
        print()
        shutil.rmtree(tmp_dir, ignore_errors=True)
        app.quit()

    QTimer.singleShot(5000, print_and_quit)

    sys.exit(app.exec())