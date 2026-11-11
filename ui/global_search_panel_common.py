#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
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
    ".git",
    ".svn",
    ".hg",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "env",
    ".idea",
    ".vscode",
    "build",
    "dist",
    "target",
]


# ============================================================
# 结果节点类型
# ============================================================
NODE_TYPE_FILE = 0
NODE_TYPE_MATCH = 1


# ============================================================
# 搜索结果树
# ============================================================

__all__ = [n for n in dir() if not n.startswith("__")]
