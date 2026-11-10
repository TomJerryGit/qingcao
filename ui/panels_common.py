#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为通用面板组件模块，包含：
- SearchBar：单文件查找/替换工具栏
- ReplaceConfirmDialog：替换确认对话框
- GotoLineDialog：跳转到行对话框
- EncodingDialog：编码选择对话框
- LineEndingDialog：行尾符选择对话框
- ThemeChooserDialog：主题选择器
- InputDialog：通用输入对话框
- ProgressDialog：进度对话框
- MessageBar：消息提示条
- StatusIndicator：状态指示器
- InlineSearchPanel：内嵌搜索面板
"""

import os
import re
import time
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QEvent, QPoint, QSettings, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPalette,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QShortcut,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QStyle,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.event_bus import SearchFinishedEvent, SearchStartedEvent, StatusMessageEvent, bus
from core.search import ReplaceEngine, SearchEngine, SearchMatch, SearchOptions, SearchResult


# ============================================================
# 常量
# ============================================================
# 搜索栏高度
SEARCH_BAR_HEIGHT = 38

# 搜索防抖延迟（毫秒）
SEARCH_DEBOUNCE_MS = 300

# 搜索历史最大长度
MAX_SEARCH_HISTORY = 30

# 常用编码
ENCODINGS = [
    ("UTF-8", "utf-8"),
    ("UTF-8 with BOM", "utf-8-sig"),
    ("GBK", "gbk"),
    ("GB2312", "gb2312"),
    ("GB18030", "gb18030"),
    ("Big5", "big5"),
    ("Shift-JIS", "shift_jis"),
    ("EUC-KR", "euc-kr"),
    ("ISO-8859-1", "iso-8859-1"),
    ("Windows-1252", "windows-1252"),
    ("UTF-16 LE", "utf-16-le"),
    ("UTF-16 BE", "utf-16-be"),
    ("ASCII", "ascii"),
]

# 行尾符
LINE_ENDINGS = [
    ("LF (\\n)", "\n"),
    ("CRLF (\\r\\n)", "\r\n"),
    ("CR (\\r)", "\r"),
]


# ============================================================
# 搜索方向枚举
# ============================================================


class SearchDirection(Enum):
    """搜索方向"""

    FORWARD = auto()
    BACKWARD = auto()


# ============================================================
# 搜索栏
# ============================================================

__all__ = [n for n in dir() if not n.startswith("__")]
