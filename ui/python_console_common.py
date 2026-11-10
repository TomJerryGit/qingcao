#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为 Python 控制台模块，包含：
- PythonConsole：Python 控制台主控件（QDockWidget）
- ConsoleOutput：输出显示控件（QPlainTextEdit 子类）
- ConsoleInput：输入行控件（带历史）
- ConsoleCompleter：代码补全器
- ConsoleHistory：命令历史管理
- InterpreterWorker：解释器执行器
- 内嵌 Python 解释器（exec）
- 执行选中代码
- 执行当前文件
- 上下文注入（api、editor、document）
- 输出捕获（stdout/stderr）
- 异常捕获与显示
- 多行输入支持
- 命令历史（上下键）
- Tab 补全
- 语法高亮
- 清空输出
- 导出输出
- 变量查看器
- 快捷键支持
"""

import builtins
import contextlib
import io
import os
import sys
import time
import traceback
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from PyQt5.QtCore import QEvent, QPoint, QSettings, QSize, QStringListModel, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QKeyEvent,
    QKeySequence,
    QPalette,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCompleter,
    QDockWidget,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollBar,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.event_bus import NotificationEvent, StatusMessageEvent, bus


# ============================================================
# 常量
# ============================================================
# 输出区域字体
DEFAULT_FONT_FAMILY = "Consolas"
DEFAULT_FONT_SIZE = 11

# 输入行字体
INPUT_FONT_FAMILY = "Consolas"
INPUT_FONT_SIZE = 12

# 最大历史记录数
MAX_HISTORY_SIZE = 200

# 最大输出行数（防止内存爆炸）
MAX_OUTPUT_LINES = 10000

# 提示符
PRIMARY_PROMPT = ">>> "
SECONDARY_PROMPT = "... "

# 颜色定义
COLOR_PROMPT = QColor("#7ec850")  # 绿色提示符
COLOR_OUTPUT = QColor("#d4d4d4")  # 普通输出
COLOR_ERROR = QColor("#f14c4c")  # 错误输出
COLOR_WARNING = QColor("#f0ad4e")  # 警告输出
COLOR_INFO = QColor("#4dabf7")  # 信息输出
COLOR_SUCCESS = QColor("#7ec850")  # 成功输出
COLOR_RESULT = QColor("#ce9178")  # 表达式结果
COLOR_COMMENT = QColor("#6a9955")  # 注释
COLOR_STRING = QColor("#ce9178")  # 字符串
COLOR_KEYWORD = QColor("#569cd6")  # 关键字
COLOR_NUMBER = QColor("#b5cea8")  # 数字

# Python 关键字
PYTHON_KEYWORDS = {
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield",
}

PYTHON_BUILTINS = {
    "abs",
    "all",
    "any",
    "bin",
    "bool",
    "bytes",
    "callable",
    "chr",
    "dict",
    "dir",
    "divmod",
    "enumerate",
    "eval",
    "filter",
    "float",
    "format",
    "frozenset",
    "getattr",
    "globals",
    "hasattr",
    "hash",
    "help",
    "hex",
    "id",
    "input",
    "int",
    "isinstance",
    "issubclass",
    "iter",
    "len",
    "list",
    "locals",
    "map",
    "max",
    "min",
    "next",
    "object",
    "oct",
    "open",
    "ord",
    "pow",
    "print",
    "range",
    "repr",
    "reversed",
    "round",
    "set",
    "setattr",
    "slice",
    "sorted",
    "str",
    "sum",
    "super",
    "tuple",
    "type",
    "vars",
    "zip",
    "__import__",
}


# ============================================================
# 历史管理器
# ============================================================

__all__ = [n for n in dir() if not n.startswith("__")]
