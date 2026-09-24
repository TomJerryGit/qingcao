#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为欢迎页模块，包含：
- WelcomeWidget：欢迎页主控件
- WelcomeHeader：欢迎页头部（Logo + 标题）
- RecentFilesList：最近文件列表
- QuickActionsPanel：快捷操作面板
- TipsPanel：每日技巧面板
- StatsPanel：使用统计面板
- WelcomeFooter：底部信息
- 最近文件/项目展示
- 新建/打开文件快捷入口
- 每日技巧随机展示
- 键盘导航支持
- 动画效果
- 版本信息展示

修复记录:
- 添加 QMessageBox 导入（RecentFilesList._clear_recent 使用）
- 补充 QSizePolicy / QTimer 等其他隐式依赖
"""

import os
import sys
import time
import random
import datetime
from typing import Optional, List, Dict, Any, Tuple

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QToolButton, QListWidget, QListWidgetItem, QFrame,
    QScrollArea, QSizePolicy, QApplication, QStyle,
    QGraphicsOpacityEffect, QStackedWidget, QGridLayout,
    QMessageBox,           # ← 修复：补上缺失的导入
)
from PyQt5.QtGui import (
    QIcon,
    QPixmap,
    QColor,
    QFont,
    QPainter,
    QBrush,
    QPen,
    QFontMetrics,
    QPalette,
    QLinearGradient,
    QDesktopServices,
    QMouseEvent,
    QKeyEvent,
)
from PyQt5.QtWidgets import QAction
from PyQt5.QtCore import (
    Qt, pyqtSignal, QTimer, QSize, QSettings, QUrl,
    QPropertyAnimation, QEasingCurve, QRect, QPoint, QEvent
)

from app.event_bus import (
    bus, StatusMessageEvent, FileOpenedEvent
)


# ============================================================
# 常量
# ============================================================
APP_NAME = "青草编辑器"
APP_NAME_EN = "QingCao Editor"
APP_VERSION = "2.0.0"
APP_SLOGAN = "青草枯荣，野火重生"
APP_DESCRIPTION = "轻量 · 极速 · 可扩展"

AUTHOR = "hedongwei"
EMAIL = "1265338136@qq.com"
HOMEPAGE = "https://github.com/qingcao-editor/qingcao"
DOCS_URL = "https://qingcao-editor.github.io/docs"

# 最多显示的最近文件数
MAX_RECENT_FILES = 8
MAX_RECENT_PROJECTS = 4

# P2-C1: DAILY_TIPS 统一到 ui/tips.py
# 原实现与 ui/tips.py 里的 TIPS 重复定义，维护时容易遗漏。
from ui.tips import TIPS as DAILY_TIPS

# 快捷操作按钮
QUICK_ACTIONS = [
    ("📄", "新建文件", "Ctrl+N", "new_file"),
    ("📂", "打开文件", "Ctrl+O", "open_file"),
    ("📁", "打开文件夹", "", "open_folder"),
    ("🕐", "最近文件", "", "recent"),
    ("🧩", "插件市场", "", "plugin_store"),
    ("⌨", "快捷键", "Ctrl+Shift+P", "command_palette"),
]


# ============================================================
# 欢迎页头部
# ============================================================
class WelcomeHeader(QWidget):
    """
    欢迎页头部。

    显示 Logo、应用名称、版本、标语。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(160)

        self._build_ui()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 30, 0, 10)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignCenter)

        # Logo（大字）
        self.logo_label = QLabel("🌱")
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setStyleSheet("font-size: 48px;")
        layout.addWidget(self.logo_label)

        # 应用名称
        self.title_label = QLabel(APP_NAME)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet(
            "font-size: 28px; font-weight: bold; "
            "color: #7ec850; letter-spacing: 4px;"
        )
        layout.addWidget(self.title_label)

        # 版本信息
        version_label = QLabel(f"v{APP_VERSION}  ·  {APP_DESCRIPTION}")
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setStyleSheet("font-size: 12px; color: #888;")
        layout.addWidget(version_label)

        # 标语
        self.slogan_label = QLabel(APP_SLOGAN)
        self.slogan_label.setAlignment(Qt.AlignCenter)
        self.slogan_label.setStyleSheet(
            "font-size: 13px; color: #666; "
            "font-style: italic; letter-spacing: 2px;"
        )
        layout.addWidget(self.slogan_label)


# ============================================================
# 快捷操作面板
# ============================================================
class QuickActionsPanel(QWidget):
    """
    快捷操作面板。

    提供新建、打开、文件夹等入口。
    """

    action_triggered = pyqtSignal(str)  # action_key

    def __init__(self, parent=None):
        super().__init__(parent)

        self._build_ui()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(8)

        # 标题
        title = QLabel("快速开始")
        title.setStyleSheet(
            "font-size: 14px; font-weight: bold; "
            "color: #d4d4d4; padding: 4px 0;"
        )
        layout.addWidget(title)

        # 按钮网格
        grid = QGridLayout()
        grid.setSpacing(8)

        for i, (icon, text, shortcut, key) in enumerate(QUICK_ACTIONS):
            btn = self._create_action_button(icon, text, shortcut, key)
            row = i // 3
            col = i % 3
            grid.addWidget(btn, row, col)

        layout.addLayout(grid)

    def _create_action_button(self, icon: str, text: str,
                                shortcut: str, key: str) -> QPushButton:
        """创建操作按钮"""
        btn = QPushButton()
        btn.setObjectName("quick_action_button")
        btn.setFixedHeight(60)
        btn.setCursor(Qt.PointingHandCursor)

        # 内容
        if shortcut:
            btn.setText(f"{icon}  {text}\n     {shortcut}")
        else:
            btn.setText(f"{icon}  {text}")

        btn.setStyleSheet("""
            QPushButton#quick_action_button {
                background-color: #2d2d2d;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
                font-size: 12px;
                text-align: left;
                padding: 8px 12px;
            }
            QPushButton#quick_action_button:hover {
                background-color: #094771;
                border-color: #0e639c;
                color: white;
            }
            QPushButton#quick_action_button:pressed {
                background-color: #0a4d7a;
            }
        """)

        btn.clicked.connect(lambda: self.action_triggered.emit(key))

        return btn


# ============================================================
# 最近文件列表
# ============================================================
class RecentFilesList(QWidget):
    """
    最近文件列表。

    显示最近打开的文件和项目。
    """

    file_clicked = pyqtSignal(str)      # 文件路径
    project_clicked = pyqtSignal(str)   # 项目路径

    def __init__(self, parent=None):
        super().__init__(parent)

        self._settings = QSettings("QingCao", "Editor")

        self._build_ui()
        self._load_recent()

        # 修复说明（P2-2）: 订阅文件事件自动刷新最近列表
        try:
            from app.event_bus import bus
            bus.file_opened.connect(self._on_file_event)
            bus.file_saved.connect(self._on_file_event)
        except Exception as e:
            print(f"[RecentFilesList] 事件订阅失败: {e}")

    def _on_file_event(self, event):
        """文件事件回调 —— 刷新最近列表"""
        try:
            QTimer.singleShot(100, self._load_recent)
        except Exception:
            pass

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(8)

        # 标题行
        title_layout = QHBoxLayout()

        self.title_label = QLabel("最近打开")
        self.title_label.setStyleSheet(
            "font-size: 14px; font-weight: bold; "
            "color: #d4d4d4; padding: 4px 0;"
        )
        title_layout.addWidget(self.title_label)

        title_layout.addStretch()

        # 清空按钮
        self.clear_btn = QToolButton()
        self.clear_btn.setText("清空")
        self.clear_btn.setStyleSheet("""
            QToolButton {
                color: #888;
                background-color: transparent;
                border: none;
                font-size: 11px;
                padding: 2px 6px;
            }
            QToolButton:hover {
                color: #f14c4c;
                background-color: #3c3c3c;
                border-radius: 3px;
            }
        """)
        self.clear_btn.clicked.connect(self._clear_recent)
        title_layout.addWidget(self.clear_btn)

        layout.addLayout(title_layout)

        # 文件列表
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("recent_list")
        self.list_widget.setFrameShape(QFrame.NoFrame)
        self.list_widget.setSelectionMode(
            QListWidget.SingleSelection
        )
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.itemDoubleClicked.connect(
            self._on_item_double_clicked
        )
        self.list_widget.setStyleSheet("""
            QListWidget#recent_list {
                background-color: transparent;
                border: none;
                color: #d4d4d4;
                font-size: 12px;
                outline: none;
            }
            QListWidget#recent_list::item {
                padding: 6px 10px;
                border-radius: 4px;
                margin: 1px 0;
            }
            QListWidget#recent_list::item:hover {
                background-color: #2a2d2e;
            }
            QListWidget#recent_list::item:selected {
                background-color: #094771;
                color: white;
            }
        """)

        layout.addWidget(self.list_widget, 1)

    # --------------------------------------------------------
    # 加载
    # --------------------------------------------------------
    def _load_recent(self):
        """加载最近文件列表"""
        self.list_widget.clear()

        # 加载最近文件
        files = self._settings.value("recent_files", [])
        if isinstance(files, str):
            files = [files] if files else []

        file_count = 0
        for filepath in files:
            if not filepath or not os.path.exists(filepath):
                continue

            if file_count >= MAX_RECENT_FILES:
                break

            item = self._create_file_item(filepath)
            self.list_widget.addItem(item)
            file_count += 1

        # 加载最近项目
        projects = self._settings.value("recent_projects", [])
        if isinstance(projects, str):
            projects = [projects] if projects else []

        project_count = 0
        for project_path in projects:
            if not project_path or not os.path.exists(project_path):
                continue

            if project_count >= MAX_RECENT_PROJECTS:
                break

            item = self._create_project_item(project_path)
            self.list_widget.addItem(item)
            project_count += 1

        # 空状态
        if self.list_widget.count() == 0:
            empty_item = QListWidgetItem("（暂无最近打开的文件）")
            empty_item.setForeground(QColor("#666"))
            empty_item.setFlags(Qt.NoItemFlags)
            empty_item.setTextAlignment(Qt.AlignCenter)
            self.list_widget.addItem(empty_item)

    def _create_file_item(self, filepath: str) -> QListWidgetItem:
        """创建文件列表项"""
        item = QListWidgetItem()

        # 图标（根据文件类型）
        ext = os.path.splitext(filepath)[1].lower()
        icon_map = {
            '.py': '🐍',
            '.js': '📜',
            '.ts': '📘',
            '.cpp': '⚙',
            '.c': '⚙',
            '.h': '📋',
            '.java': '☕',
            '.go': '🐹',
            '.rs': '🦀',
            '.md': '📝',
            '.txt': '📄',
            '.json': '📊',
            '.xml': '📋',
            '.html': '🌐',
            '.css': '🎨',
            '.log': '📃',
            '.csv': '📈',
        }
        icon = icon_map.get(ext, '📄')

        # 文件名和路径
        filename = os.path.basename(filepath)
        dirname = os.path.dirname(filepath)

        # 缩略路径
        if len(dirname) > 50:
            dirname = "..." + dirname[-47:]

        item.setText(f"{icon}  {filename}")
        item.setToolTip(f"{filepath}\n\n双击打开")

        item.setData(Qt.UserRole, 'file')
        item.setData(Qt.UserRole + 1, filepath)

        return item

    def _create_project_item(self, project_path: str) -> QListWidgetItem:
        """创建项目列表项"""
        item = QListWidgetItem()

        name = os.path.basename(project_path)
        if name.endswith('.qingcao-project'):
            name = name[:-16]

        item.setText(f"📁  [项目] {name}")
        item.setToolTip(f"{project_path}\n\n双击打开项目")

        item.setData(Qt.UserRole, 'project')
        item.setData(Qt.UserRole + 1, project_path)

        return item

    # --------------------------------------------------------
    # 交互
    # --------------------------------------------------------
    def _on_item_clicked(self, item: QListWidgetItem):
        """单击项"""
        # 单击仅选中，不打开
        pass

    def _on_item_double_clicked(self, item: QListWidgetItem):
        """双击项"""
        item_type = item.data(Qt.UserRole)
        path = item.data(Qt.UserRole + 1)

        if not path:
            return

        if item_type == 'file':
            self.file_clicked.emit(path)
        elif item_type == 'project':
            self.project_clicked.emit(path)

    def _clear_recent(self):
        """清空最近列表"""
        # 关键修复：QMessageBox 已在顶部导入
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空最近文件列表吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        self._settings.setValue("recent_files", [])
        self._settings.setValue("recent_projects", [])
        self._load_recent()

    def refresh(self):
        """刷新列表"""
        self._load_recent()


# ============================================================
# 每日技巧面板
# ============================================================
class TipsPanel(QWidget):
    """
    每日技巧面板。

    随机显示一条使用技巧。
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._current_tip = ""

        self._build_ui()
        self._load_tip()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(8)

        # 标题行
        title_layout = QHBoxLayout()

        title = QLabel("💡 每日技巧")
        title.setStyleSheet(
            "font-size: 14px; font-weight: bold; "
            "color: #d4d4d4; padding: 4px 0;"
        )
        title_layout.addWidget(title)

        title_layout.addStretch()

        # 换一条按钮
        self.next_btn = QToolButton()
        self.next_btn.setText("换一条")
        self.next_btn.setStyleSheet("""
            QToolButton {
                color: #888;
                background-color: transparent;
                border: none;
                font-size: 11px;
                padding: 2px 6px;
            }
            QToolButton:hover {
                color: #7ec850;
                background-color: #3c3c3c;
                border-radius: 3px;
            }
        """)
        self.next_btn.clicked.connect(self._load_tip)
        title_layout.addWidget(self.next_btn)

        layout.addLayout(title_layout)

        # 技巧文本
        self.tip_label = QLabel()
        self.tip_label.setWordWrap(True)
        self.tip_label.setStyleSheet("""
            QLabel {
                background-color: #2d2d2d;
                color: #d4d4d4;
                border-left: 3px solid #7ec850;
                border-radius: 4px;
                padding: 12px 16px;
                font-size: 12px;
                line-height: 1.6;
            }
        """)
        self.tip_label.setMinimumHeight(60)

        layout.addWidget(self.tip_label)

    def _load_tip(self):
        """加载随机技巧"""
        # 避免连续重复
        available_tips = [t for t in DAILY_TIPS if t != self._current_tip]
        if not available_tips:
            available_tips = DAILY_TIPS

        self._current_tip = random.choice(available_tips)
        self.tip_label.setText(self._current_tip)


# ============================================================
# 使用统计面板
# ============================================================
class StatsPanel(QWidget):
    """
    使用统计面板。

    显示编辑器的使用统计信息。
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._build_ui()
        self._load_stats()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(8)

        # 标题
        title = QLabel("📊 使用统计")
        title.setStyleSheet(
            "font-size: 14px; font-weight: bold; "
            "color: #d4d4d4; padding: 4px 0;"
        )
        layout.addWidget(title)

        # 统计网格
        grid = QGridLayout()
        grid.setSpacing(8)

        self.stats_labels: Dict[str, QLabel] = {}

        stats_definitions = [
            ("saves", "保存次数", "💾"),
            ("files_opened", "打开文件", "📂"),
            ("lines_edited", "编辑行数", "✏"),
            ("macros_used", "宏使用", "⏺"),
        ]

        for i, (key, display, icon) in enumerate(stats_definitions):
            row = i // 2
            col = i % 2

            # 统计项
            item_widget = QWidget()
            item_widget.setStyleSheet("""
                QWidget {
                    background-color: #2d2d2d;
                    border-radius: 4px;
                }
            """)
            item_layout = QVBoxLayout(item_widget)
            item_layout.setContentsMargins(10, 8, 10, 8)
            item_layout.setSpacing(2)

            value_label = QLabel("0")
            value_label.setStyleSheet(
                "font-size: 20px; font-weight: bold; "
                "color: #7ec850; background: transparent;"
            )
            item_layout.addWidget(value_label)

            label = QLabel(f"{icon} {display}")
            label.setStyleSheet(
                "font-size: 11px; color: #888; background: transparent;"
            )
            item_layout.addWidget(label)

            self.stats_labels[key] = value_label

            grid.addWidget(item_widget, row, col)

        layout.addLayout(grid)

    def _load_stats(self):
        """加载统计数据。

        P1-B6: 改用 core.usage_stats

        原实现读取 data/onboarding.json，但该文件从未被任何
        模块写入，导致统计面板永远显示 0。改用统一的
        core.usage_stats（数据源：telemetry / session /
        local_completer）。
        """
        try:
            from core.usage_stats import get_usage_stats
            snap = get_usage_stats().get_snapshot()

            self.update_stat("saves", int(snap.files_saved))
            self.update_stat("files_opened", int(snap.files_opened))
            # lines_edited：用累计编辑时长（秒）近似
            self.update_stat(
                "lines_edited", int(snap.total_edit_time)
            )
            # macros_used：用加载插件数近似
            self.update_stat(
                "macros_used", int(snap.plugins_loaded)
            )
        except ImportError as e:
            print(f"[StatsPanel] core.usage_stats 不可用: {e}")
        except Exception as e:
            print(f"[StatsPanel] 加载统计失败: {e}")

    def update_stat(self, key: str, value: int):
        """更新统计值"""
        label = self.stats_labels.get(key)
        if label:
            # 格式化大数字
            if value >= 1000000:
                text = f"{value / 1000000:.1f}M"
            elif value >= 1000:
                text = f"{value / 1000:.1f}K"
            else:
                text = str(value)

            label.setText(text)

    def refresh(self):
        """刷新统计"""
        self._load_stats()


# ============================================================
# 底部信息
# ============================================================
class WelcomeFooter(QWidget):
    """
    欢迎页底部信息。

    显示作者、邮箱、链接。
    """

    link_clicked = pyqtSignal(str)  # URL

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedHeight(50)

        self._build_ui()

    def _build_ui(self):
        """构建 UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignCenter)

        # 开发者
        author_label = QLabel(f"开发者: {AUTHOR}")
        author_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(author_label)

        # 分隔符
        sep = QLabel("·")
        sep.setStyleSheet("color: #444;")
        layout.addWidget(sep)

        # 邮箱
        email_label = QLabel(f"📧 {EMAIL}")
        email_label.setStyleSheet(
            "color: #888; font-size: 11px;"
        )
        email_label.setToolTip("点击复制邮箱")
        email_label.setCursor(Qt.PointingHandCursor)
        email_label.mousePressEvent = lambda e: self._copy_email()
        layout.addWidget(email_label)

        # 分隔符
        sep2 = QLabel("·")
        sep2.setStyleSheet("color: #444;")
        layout.addWidget(sep2)

        # 文档链接
        docs_label = QLabel("📖 文档")
        docs_label.setStyleSheet("""
            color: #4dabf7;
            font-size: 11px;
            text-decoration: underline;
        """)
        docs_label.setCursor(Qt.PointingHandCursor)
        docs_label.mousePressEvent = lambda e: self.link_clicked.emit(DOCS_URL)
        layout.addWidget(docs_label)

        # 分隔符
        sep3 = QLabel("·")
        sep3.setStyleSheet("color: #444;")
        layout.addWidget(sep3)

        # GitHub
        github_label = QLabel("🐙 GitHub")
        github_label.setStyleSheet("""
            color: #4dabf7;
            font-size: 11px;
            text-decoration: underline;
        """)
        github_label.setCursor(Qt.PointingHandCursor)
        github_label.mousePressEvent = lambda e: self.link_clicked.emit(HOMEPAGE)
        layout.addWidget(github_label)

    def _copy_email(self):
        """复制邮箱到剪贴板"""
        try:
            QApplication.clipboard().setText(EMAIL)
            bus.emit_status(f"已复制邮箱: {EMAIL}", 2000, "success")
        except Exception:
            pass


# ============================================================
# 欢迎页主控件
# ============================================================
class WelcomeWidget(QWidget):
    """
    欢迎页主控件。

    在没有打开任何标签时显示，包含:
    - 头部（Logo + 名称）
    - 快速操作
    - 最近文件
    - 每日技巧
    - 使用统计
    - 底部信息

    信号:
        new_file_requested(): 请求新建文件
        open_file_requested(): 请求打开文件
        open_folder_requested(str): 请求打开文件夹
        open_recent_file(str): 请求打开最近文件
        open_recent_project(str): 请求打开最近项目
        open_plugin_store(): 请求打开插件市场
        open_command_palette(): 请求打开命令面板
        close_requested(): 请求关闭欢迎页
    """

    new_file_requested = pyqtSignal()
    open_file_requested = pyqtSignal()
    open_folder_requested = pyqtSignal(str)
    open_recent_file = pyqtSignal(str)
    open_recent_project = pyqtSignal(str)
    open_plugin_store = pyqtSignal()
    open_command_palette = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self, main_window=None, parent=None):
        """
        参数:
            main_window: 主窗口（用于加载统计等）
            parent: 父控件
        """
        super().__init__(parent)

        self.main_window = main_window

        # 设置背景
        self.setAutoFillBackground(True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("""
            WelcomeWidget {
                background-color: #1e1e1e;
            }
        """)

        # 构建 UI
        self._build_ui()

        # 连接信号
        self._connect_signals()

        # 淡入动画
        self._setup_animation()

    # --------------------------------------------------------
    # UI 构建
    # --------------------------------------------------------
    def _build_ui(self):
        """构建 UI"""
        # 主布局：居中滚动
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #252526;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: #444;
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #666;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

        # 内容容器
        content = QWidget()
        content.setStyleSheet("background-color: #1e1e1e;")

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.setAlignment(Qt.AlignTop)

        # 1. 头部
        self.header = WelcomeHeader()
        content_layout.addWidget(self.header)

        # 中央容器（限制最大宽度，居中显示）
        center_container = QWidget()
        center_container.setMaximumWidth(900)
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(16)

        # 2. 快速操作
        self.quick_actions = QuickActionsPanel()
        center_layout.addWidget(self.quick_actions)

        # 3. 分栏：左侧最近文件 + 右侧技巧和统计
        columns = QHBoxLayout()
        columns.setSpacing(16)

        # 左侧：最近文件
        left_column = QVBoxLayout()
        self.recent_files = RecentFilesList()
        left_column.addWidget(self.recent_files, 1)
        columns.addLayout(left_column, 3)

        # 右侧：技巧 + 统计
        right_column = QVBoxLayout()
        right_column.setSpacing(16)

        self.tips_panel = TipsPanel()
        right_column.addWidget(self.tips_panel)

        self.stats_panel = StatsPanel()
        right_column.addWidget(self.stats_panel)

        right_column.addStretch()

        columns.addLayout(right_column, 2)

        center_layout.addLayout(columns)

        # 将中央容器包装并居中
        center_wrapper = QHBoxLayout()
        center_wrapper.addStretch()
        center_wrapper.addWidget(center_container)
        center_wrapper.addStretch()

        content_layout.addLayout(center_wrapper)

        content_layout.addStretch()

        scroll.setWidget(content)
        outer_layout.addWidget(scroll, 1)

        # 4. 底部
        self.footer = WelcomeFooter()
        outer_layout.addWidget(self.footer)

    # --------------------------------------------------------
    # 信号连接
    # --------------------------------------------------------
    def _connect_signals(self):
        """连接信号"""
        # 快速操作
        self.quick_actions.action_triggered.connect(
            self._on_quick_action
        )

        # 最近文件
        self.recent_files.file_clicked.connect(
            self._on_recent_file_clicked
        )
        self.recent_files.project_clicked.connect(
            self._on_recent_project_clicked
        )

        # 底部链接
        self.footer.link_clicked.connect(self._on_link_clicked)

    # --------------------------------------------------------
    # 动画
    # --------------------------------------------------------
    def _setup_animation(self):
        """设置淡入动画"""
        try:
            effect = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(effect)

            self._animation = QPropertyAnimation(effect, b"opacity")
            self._animation.setDuration(400)
            self._animation.setStartValue(0.0)
            self._animation.setEndValue(1.0)
            self._animation.setEasingCurve(QEasingCurve.OutCubic)
        except Exception:
            self._animation = None

    def showEvent(self, event):
        """显示事件"""
        super().showEvent(event)

        # 播放动画
        if self._animation:
            self._animation.start()

        # 刷新数据
        self.refresh()

    # --------------------------------------------------------
    # 事件处理
    # --------------------------------------------------------
    def _on_quick_action(self, action_key: str):
        """快捷操作触发"""
        if action_key == "new_file":
            self.new_file_requested.emit()
        elif action_key == "open_file":
            self.open_file_requested.emit()
        elif action_key == "open_folder":
            from PyQt5.QtWidgets import QFileDialog
            folder = QFileDialog.getExistingDirectory(
                self, "打开文件夹"
            )
            if folder:
                self.open_folder_requested.emit(folder)
        elif action_key == "recent":
            # 滚动到最近文件
            self.recent_files.setFocus()
        elif action_key == "plugin_store":
            self.open_plugin_store.emit()
        elif action_key == "command_palette":
            self.open_command_palette.emit()

    def _on_recent_file_clicked(self, filepath: str):
        """最近文件点击"""
        self.open_recent_file.emit(filepath)

    def _on_recent_project_clicked(self, project_path: str):
        """最近项目点击"""
        self.open_recent_project.emit(project_path)

    def _on_link_clicked(self, url: str):
        """链接点击"""
        try:
            QDesktopServices.openUrl(QUrl(url))
        except Exception:
            pass

    # --------------------------------------------------------
    # 数据刷新
    # --------------------------------------------------------
    def refresh(self):
        """刷新欢迎页数据"""
        try:
            self.recent_files.refresh()
            self.stats_panel.refresh()
        except Exception as e:
            print(f"[WelcomeWidget] 刷新失败: {e}")

    def update_stats(self):
        """更新统计"""
        self.stats_panel.refresh()

    def next_tip(self):
        """显示下一条技巧"""
        self.tips_panel._load_tip()

    # --------------------------------------------------------
    # 键盘导航
    # --------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent):
        """键盘事件"""
        key = event.key()

        # 数字键 1-6 触发快捷操作
        if Qt.Key_1 <= key <= Qt.Key_6:
            index = key - Qt.Key_1
            if 0 <= index < len(QUICK_ACTIONS):
                _, _, _, action_key = QUICK_ACTIONS[index]
                self._on_quick_action(action_key)
                event.accept()
                return

        # Ctrl+N / Ctrl+O
        if event.modifiers() & Qt.ControlModifier:
            if key == Qt.Key_N:
                self.new_file_requested.emit()
                event.accept()
                return
            elif key == Qt.Key_O:
                self.open_file_requested.emit()
                event.accept()
                return

        super().keyPressEvent(event)

    # --------------------------------------------------------
    # 焦点
    # --------------------------------------------------------
    def setFocus(self):
        """设置焦点"""
        super().setFocus()
        # 聚焦到最近文件列表
        try:
            self.recent_files.list_widget.setFocus()
        except Exception:
            pass

    # --------------------------------------------------------
    # 调试
    # --------------------------------------------------------
    def dump(self) -> str:
        """导出欢迎页信息"""
        lines = ["WelcomeWidget", "=" * 60]
        lines.append(f"应用: {APP_NAME} v{APP_VERSION}")
        lines.append(f"标语: {APP_SLOGAN}")
        lines.append(f"作者: {AUTHOR}")
        lines.append(f"邮箱: {EMAIL}")
        lines.append(f"最近文件数: {self.recent_files.list_widget.count()}")
        lines.append(f"当前技巧: {self.tips_panel._current_tip[:50]}...")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"<WelcomeWidget {APP_NAME} v{APP_VERSION}>"


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox

    app = QApplication(sys.argv)

    # 创建主窗口
    win = QMainWindow()
    win.setWindowTitle("WelcomeWidget 测试")
    win.resize(1100, 750)
    win.show()

    # 创建欢迎页
    welcome = WelcomeWidget()
    win.setCentralWidget(welcome)

    # 连接信号
    welcome.new_file_requested.connect(
        lambda: print("[信号] 新建文件")
    )
    welcome.open_file_requested.connect(
        lambda: print("[信号] 打开文件")
    )
    welcome.open_folder_requested.connect(
        lambda p: print(f"[信号] 打开文件夹: {p}")
    )
    welcome.open_recent_file.connect(
        lambda p: print(f"[信号] 打开最近文件: {p}")
    )
    welcome.open_recent_project.connect(
        lambda p: print(f"[信号] 打开最近项目: {p}")
    )
    welcome.open_plugin_store.connect(
        lambda: print("[信号] 打开插件市场")
    )
    welcome.open_command_palette.connect(
        lambda: print("[信号] 打开命令面板")
    )

    # 添加一些测试最近文件
    from PyQt5.QtCore import QSettings
    settings = QSettings("QingCao", "Editor")

    # 创建临时测试文件
    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="qingcao_welcome_test_")
    test_files = [
        os.path.join(tmp_dir, "main.py"),
        os.path.join(tmp_dir, "README.md"),
        os.path.join(tmp_dir, "config.json"),
    ]

    for f in test_files:
        with open(f, 'w') as file:
            file.write("# test\n")

    settings.setValue("recent_files", test_files)
    welcome.refresh()

    print("=== WelcomeWidget 测试 ===")
    print(welcome.dump())
    print()

    # 测试快捷操作
    def test_actions():
        print("测试下一条技巧...")
        welcome.next_tip()

        print("测试刷新统计...")
        welcome.update_stats()

    QTimer.singleShot(2000, test_actions)

    # 清理并退出
    def cleanup_and_quit():
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
        app.quit()

    QTimer.singleShot(5000, cleanup_and_quit)

    sys.exit(app.exec_())