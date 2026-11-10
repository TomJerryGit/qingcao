#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为项目目录树模块，包含：
- DirectoryTree：项目目录树面板
- DirectoryTreeModel：目录树数据模型
- FileSystemWatcher：文件系统监听
- 目录递归加载与懒加载
- 文件/文件夹增删改操作
- Git 状态着色
- 多选与批量操作
- 右键上下文菜单
- 文件过滤（隐藏文件、排除规则）
- 文件图标
- 拖放支持
- 搜索过滤
- 路径收藏与书签
- 刷新与自动刷新
- 打开方式集成
"""

import fnmatch
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple

from PyQt5.QtCore import (
    QDir,
    QFileInfo,
    QFileSystemWatcher,
    QMimeData,
    QModelIndex,
    Qt,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QDrag,
    QFont,
    QIcon,
    QKeySequence,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAction,
    QApplication,
    QFileDialog,
    QFileIconProvider,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


# ============================================================
# 常量
# ============================================================
# 默认排除目录
DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".svn",
    ".hg",
    ".bzr",
    "__pycache__",
    "__MACOSX",
    "node_modules",
    ".npm",
    ".yarn",
    ".venv",
    "venv",
    "env",
    ".env",
    ".idea",
    ".vscode",
    ".vs",
    "build",
    "dist",
    "target",
    "out",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "bin",
    "obj",
}

# Git 状态颜色
GIT_STATUS_COLORS = {
    "M": QColor("#E5A72D"),  # 已修改（橙）
    "A": QColor("#6A9955"),  # 新增（绿）
    "D": QColor("#F14C4C"),  # 删除（红）
    "?": QColor("#808080"),  # 未跟踪（灰）
    "R": QColor("#4DABF7"),  # 重命名（蓝）
    "C": QColor("#4DABF7"),  # 复制（蓝）
    "U": QColor("#FF6B6B"),  # 冲突（红）
}

# 文件类型图标颜色（用作彩色小方块）
FILE_TYPE_COLORS = {
    ".py": QColor("#3572A5"),
    ".pyw": QColor("#3572A5"),
    ".js": QColor("#F1E05A"),
    ".ts": QColor("#2B7489"),
    ".jsx": QColor("#61DAFB"),
    ".tsx": QColor("#61DAFB"),
    ".java": QColor("#B07219"),
    ".cpp": QColor("#F34B7D"),
    ".cc": QColor("#F34B7D"),
    ".cxx": QColor("#F34B7D"),
    ".h": QColor("#F34B7D"),
    ".hpp": QColor("#F34B7D"),
    ".c": QColor("#555555"),
    ".rs": QColor("#DEA584"),
    ".go": QColor("#00ADD8"),
    ".rb": QColor("#701516"),
    ".php": QColor("#4F5D95"),
    ".swift": QColor("#FFAC45"),
    ".kt": QColor("#A97BFF"),
    ".html": QColor("#E34C26"),
    ".htm": QColor("#E34C26"),
    ".css": QColor("#563D7C"),
    ".scss": QColor("#C6538C"),
    ".json": QColor("#F1E05A"),
    ".xml": QColor("#0060AC"),
    ".yaml": QColor("#CB171E"),
    ".yml": QColor("#CB171E"),
    ".toml": QColor("#9C4221"),
    ".md": QColor("#083FA1"),
    ".rst": QColor("#141414"),
    ".txt": QColor("#999999"),
    ".log": QColor("#C0C0C0"),
    ".csv": QColor("#1E8E3E"),
    ".sql": QColor("#E38C00"),
    ".sh": QColor("#89E051"),
    ".bat": QColor("#C1F12E"),
    ".ps1": QColor("#012456"),
    ".ini": QColor("#999999"),
    ".cfg": QColor("#999999"),
    ".conf": QColor("#999999"),
}

# 文件排序优先级
FILE_SORT_PRIORITY = {
    "dir": 0,
    "file": 1,
}

# 节点类型
NODE_TYPE_DIR = 0
NODE_TYPE_FILE = 1
NODE_TYPE_ROOT = 2


# ============================================================
# 节点类型枚举
# ============================================================


class NodeType(Enum):
    """节点类型"""

    ROOT = auto()
    DIRECTORY = auto()
    FILE = auto()
    SYMLINK = auto()


# ============================================================
# 目录树数据模型
# ============================================================

__all__ = [n for n in dir() if not n.startswith("__")]
