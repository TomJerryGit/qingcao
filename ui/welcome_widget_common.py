#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
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

import datetime
import os
import random
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSettings,
    QSize,
    Qt,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QIcon,
    QKeyEvent,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,  # ← 修复：补上缺失的导入
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.event_bus import FileOpenedEvent, StatusMessageEvent, bus
from core.i18n_json import tr as _tr
from core.i18n_json import tr_menu as _tr_menu


# ============================================================
# 主题色（欢迎页此前是**硬编码深色**，导致护眼等浅色主题下
# 出现"深色欢迎页 + 浅色工具栏"的割裂观感）
#
# `C` 是"当前主题颜色"的**模块级代理**：所有样式表通过它的属性
# 读取颜色，因此切换主题后只要重新执行一次样式构建即可生效。
# 见 WelcomeWidget.refresh_theme。
# ============================================================
class _ThemeProxy:
    """主题颜色代理：属性取值来自当前主题，缺失时回退 Dark+ 默认值"""

    def __init__(self):
        self._colors = None

    def bind(self, colors) -> None:
        self._colors = colors

    def __getattr__(self, name: str):
        colors = self.__dict__.get("_colors")
        if colors is not None:
            val = getattr(colors, name, None)
            if val:
                return val
        # 回退：内置暗色主题的取值（保证任何情况下都能渲染）
        from infrastructure.theme_loader import BuiltinThemes

        return getattr(BuiltinThemes.dark_night().colors, name, "#1e1e1e")


C = _ThemeProxy()

# 首次导入即绑定默认主题，避免在主题系统初始化前访问 C 出错
try:
    from infrastructure.theme_loader import BuiltinThemes as _BT

    C.bind(_BT.dark_night().colors)
except Exception:  # pragma: no cover
    pass


# ============================================================
# 常量
# ============================================================
APP_NAME = "青草编辑器"
APP_NAME_EN = "QingCao Editor"
# P1-1: 版本号唯一来源 version.py
try:
    from version import __version__ as APP_VERSION
except ImportError:  # pragma: no cover
    APP_VERSION = "0.0.0"
APP_SLOGAN = "青草枯荣，野火重生"
APP_DESCRIPTION = "轻量 · 极速 · 可扩展"

# QSettings 组织名（与 main.py 的 ORG_NAME 保持一致）
ORG_NAME = "QingCao"

AUTHOR = "TomJerry"
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

__all__ = [n for n in dir() if not n.startswith("__")]
