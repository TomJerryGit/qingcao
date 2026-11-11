#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为快捷键编辑器模块，包含：
- KeymapEditor：快捷键编辑器主对话框
- KeyCaptureDialog：按键捕获对话框
- KeymapTable：快捷键表格控件
- KeymapSearchBar：快捷键搜索栏
- KeymapProfile：快捷键方案（多套方案切换）
- 命令列表与分类
- 快捷键冲突检测
- 导入/导出快捷键
- 恢复默认
- 实时搜索过滤
- 分类折叠
"""

import json
import os
import sys
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from PyQt5.QtCore import QPoint, QSettings, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.actions import ActionManager
from app.event_bus import StatusMessageEvent, bus
from core.keymap_profiles import (
    apply_scheme,
    get_scheme_names,
    validate_scheme,
)


# ============================================================
# 快捷键方案（core/keymap_profiles）的持久化
# ============================================================
# 为什么放在这个模块而不是 core：
#   `core/keymap_profiles.py` 是**纯逻辑**（不依赖 PyQt/QSettings），
#   便于被测试与脚本直接使用；持久化属于 UI 层职责。
#
# QSettings 用 ("QingCao", "Editor")，与全仓其它设置同源
# （见 config_manager / preferences / plugins 的既有用法）。
KEYMAP_SCHEME_SETTINGS_KEY = "keymap/scheme"


def _scheme_settings():
    """取方案设置对象（独立函数便于测试替换）"""
    return QSettings("QingCao", "Editor")


def load_saved_scheme() -> str:
    """读取用户上次选择的快捷键方案 key（默认 "default"）"""
    try:
        val = _scheme_settings().value(KEYMAP_SCHEME_SETTINGS_KEY, "default")
        key = str(val or "default")
        # 方案可能被改名/删除，回退到 default 以免启动时报错
        valid = {k for k, _ in get_scheme_names()}
        return key if key in valid else "default"
    except Exception:
        return "default"


def save_scheme(key: str) -> bool:
    """记住用户选择的方案 key"""
    try:
        _scheme_settings().setValue(KEYMAP_SCHEME_SETTINGS_KEY, str(key))
        return True
    except Exception:
        return False


def apply_saved_scheme(action_manager) -> bool:
    """启动时应用用户已保存的快捷键方案

    返回:
        True 表示确实应用了一个**非默认**方案；False 表示无需应用
        （未保存过 / 保存的是 default / 应用失败）

    为什么需要"启动时应用"：方案只存在 QSettings 里而不在启动时生效的话，
    用户重启后快捷键会**悄悄回到默认**，功能形同虚设。
    """
    key = load_saved_scheme()
    if key == "default":
        return False
    if action_manager is None:
        return False
    return bool(apply_scheme(action_manager, key))


# ============================================================
# 常量
# ============================================================
# 快捷键配置文件
KEYBINDINGS_FILE = "keybindings.json"
KEYMAP_DIR = "keymaps"

# 冲突颜色
CONFLICT_COLOR = QColor("#f14c4c")
DUPLICATE_COLOR = QColor("#f0ad4e")
NORMAL_COLOR = QColor("#d4d4d4")
RESERVED_COLOR = QColor("#888888")

# 保留快捷键（系统级）
RESERVED_SHORTCUTS = {
    "Ctrl+Alt+Delete",
    "Alt+F4",
    "Ctrl+Alt+F1",
    "Ctrl+Alt+F2",
}

# 分类显示名称映射
CATEGORY_DISPLAY_NAMES = {
    "文件": "文件",
    "编辑": "编辑",
    "视图": "视图",
    "搜索": "搜索",
    "工具": "工具",
    "宏": "宏",
    "帮助": "帮助",
    "插件": "插件",
    "其他": "其他",
    "File": "文件",
    "Edit": "编辑",
    "View": "视图",
    "Search": "搜索",
    "Tools": "工具",
    "Macro": "宏",
    "Help": "帮助",
    "Plugin": "插件",
    "Other": "其他",
}

# 分类排序优先级
CATEGORY_ORDER = [
    "文件",
    "编辑",
    "视图",
    "搜索",
    "工具",
    "宏",
    "插件",
    "帮助",
    "其他",
]


# ============================================================
# 快捷键记录
# ============================================================
@dataclass
class KeymapEntry:
    """快捷键记录"""

    name: str = ""  # 动作名称
    text: str = ""  # 显示文本
    category: str = "其他"  # 分类
    shortcut: str = ""  # 当前快捷键
    default: str = ""  # 默认快捷键
    description: str = ""  # 描述
    conflicts: List[str] = field(default_factory=list)  # 冲突的动作名

    @property
    def is_default(self) -> bool:
        """是否为默认值"""
        return self.shortcut == self.default

    @property
    def is_empty(self) -> bool:
        """是否为空快捷键"""
        return not self.shortcut

    @property
    def has_conflict(self) -> bool:
        """是否有冲突"""
        return len(self.conflicts) > 0

    def __repr__(self) -> str:
        return f"<KeymapEntry {self.name} '{self.shortcut}' (default: {self.default})>"


# ============================================================
# 快捷键方案
# ============================================================
@dataclass
class KeymapProfile:
    """快捷键方案"""

    name: str = "默认"
    description: str = ""
    shortcuts: Dict[str, str] = field(default_factory=dict)
    created_at: str = ""
    author: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "shortcuts": dict(self.shortcuts),
            "created_at": self.created_at,
            "author": self.author,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "KeymapProfile":
        return cls(
            name=d.get("name", "未命名"),
            description=d.get("description", ""),
            shortcuts=dict(d.get("shortcuts", {})),
            created_at=d.get("created_at", ""),
            author=d.get("author", ""),
        )

    def save(self, filepath: str) -> bool:
        """保存到文件"""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[KeymapProfile] 保存失败: {e}")
            return False

    @classmethod
    def load(cls, filepath: str) -> Optional["KeymapProfile"]:
        """从文件加载"""
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            print(f"[KeymapProfile] 加载失败: {e}")
            return None


# ============================================================
# 按键捕获对话框
# ============================================================

__all__ = [n for n in dir() if not n.startswith("__")]
