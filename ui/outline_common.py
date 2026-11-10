#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为符号大纲面板模块，包含：
- OutlinePanel：符号大纲面板（QDockWidget，基础/增强两种模式）
- OutlineTree：符号树控件（QTreeWidget）
- SymbolParser：符号解析器（正则 + 简单语法分析）
- SymbolNode：符号节点数据类
- SymbolType：符号类型枚举
- 多语言符号解析（Python/JS/TS/C++/Java/Go/Rust 等）
- 层级结构展示
- 符号类型图标
- 搜索过滤
- 类型筛选（增强模式）
- 排序切换（增强模式）
- 面包屑导航（增强模式）
- 跟随光标高亮（增强模式）
- 双击跳转
- 右键菜单
- 自动更新
- 折叠/展开
- 符号统计

合并说明（P3-8）:
    原文件 ui/outline_panel.py 与 ui/outline_panel_enhanced.py 已合并到
    本文件。通过 OutlinePanel(enhanced=True) 启用增强功能（面包屑、
    筛选、排序、跟随光标）。原 OutlinePanelEnhanced 类已删除。
    调用方（如 ui/main_window.py）请使用 OutlinePanel(..., enhanced=True)。
"""

import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QPoint, QSettings, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAction,
    QApplication,
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QStyle,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.event_bus import CursorEvent, EditorChangedEvent, FileOpenedEvent, StatusMessageEvent, bus


# ============================================================
# 常量
# ============================================================
# 自动更新延迟（毫秒）
UPDATE_DELAY_MS = 500

# 最大解析行数（防止超大文件卡顿）
MAX_PARSE_LINES = 50000

# 符号类型
SYMBOL_TYPES = {
    "class": "类",
    "function": "函数",
    "method": "方法",
    "variable": "变量",
    "constant": "常量",
    "module": "模块",
    "import": "导入",
    "interface": "接口",
    "struct": "结构体",
    "enum": "枚举",
    "namespace": "命名空间",
    "property": "属性",
    "field": "字段",
    "constructor": "构造函数",
    "decorator": "装饰器",
    "macro": "宏",
    "type": "类型",
}

# 符号类型颜色（用于标识）
SYMBOL_TYPE_COLORS = {
    "class": QColor("#4EC9B0"),
    "function": QColor("#DCDCAA"),
    "method": QColor("#DCDCAA"),
    "variable": QColor("#9CDCFE"),
    "constant": QColor("#4FC1FF"),
    "module": QColor("#C586C0"),
    "import": QColor("#808080"),
    "interface": QColor("#4EC9B0"),
    "struct": QColor("#4EC9B0"),
    "enum": QColor("#4EC9B0"),
    "namespace": QColor("#C586C0"),
    "property": QColor("#9CDCFE"),
    "field": QColor("#9CDCFE"),
    "constructor": QColor("#DCDCAA"),
    "decorator": QColor("#C586C0"),
    "macro": QColor("#C586C0"),
    "type": QColor("#4EC9B0"),
}

# 符号类型图标（Unicode 符号）
SYMBOL_TYPE_ICONS = {
    "class": "🔷",
    "function": "🔧",
    "method": "⚙",
    "variable": "📦",
    "constant": "🔒",
    "module": "📁",
    "import": "📥",
    "interface": "🔶",
    "struct": "🔸",
    "enum": "🔹",
    "namespace": "📂",
    "property": "🏷",
    "field": "📌",
    "constructor": "🏗",
    "decorator": "✨",
    "macro": "⚡",
    "type": "🔺",
}

# 树列索引
COL_SYMBOL = 0
COL_LINE = 1
COL_TYPE = 2

# 增强模式：筛选类别（合并自 outline_panel_enhanced.py）
FILTER_CATEGORIES = {
    "all": "全部",
    "class": "类/接口",
    "function": "函数",
    "method": "方法",
    "variable": "变量",
    "constant": "常量",
}

# 增强模式：排序选项（合并自 outline_panel_enhanced.py）
SORT_OPTIONS = {
    "line": "按行号",
    "name": "按名称",
    "type": "按类型",
}


# ============================================================
# 符号类型枚举
# ============================================================

__all__ = [n for n in dir() if not n.startswith("__")]
