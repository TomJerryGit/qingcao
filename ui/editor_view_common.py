#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为编辑器视图模块，包含：
- EditorWidget：QScintilla 子类（编辑器控件）
- 智能按键处理（括号/引号包裹、跳过、删除成对符号）
- Home 键智能循环跳转
- Ctrl+Backspace 按词删除
- Tab/Shift+Tab 智能缩进
- 代码片段触发
- 列模式与多光标
- 智能单词高亮触发
- 光标拖尾触发
- 缩进彩虹线绘制
- 书签标记
- LSP 诊断指示器
- 右键上下文菜单
- 拖放文件支持
- 智能字符统计
- 鼠标事件处理

修复记录:
- _wrap_selection: 使用字节长度计算选区偏移，修复中文选区错误
- _smart_home: 使用字节长度计算缩进位置
- _try_delete_pair: 增加非 ASCII 字节过滤
- paintEvent: 移除未使用的 margin_width；缓存行高；跳过不可见/空行
- 其余行为保持与原实现一致
"""

import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from PyQt5 import Qsci
from PyQt5.Qsci import QsciScintilla
from PyQt5.QtCore import (
    QEvent,
    QMimeData,
    QPoint,
    QRectF,
    Qt,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QContextMenuEvent,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QWheelEvent,
)
from PyQt5.QtWidgets import QApplication, QMenu, QMessageBox, QToolTip

from app.preferences import Preferences
from core.content_provider import MemoryProvider
from core.document import Document, LocalFileProvider
from core.editor import EditorProxy
from core.local_completer import get_local_completer


# ============================================================
# 常量
# ============================================================
# 指示器 ID（与 EditorProxy 中对应）
INDICATOR_SEARCH = 0
INDICATOR_CURRENT_MATCH = 1
INDICATOR_LSP_ERROR = 2
INDICATOR_SNIPPET = 3
INDICATOR_CURSOR_TRAIL = 5
INDICATOR_SMART_HIGHLIGHT = 7
# v2.4：插件装饰（背景色块，见 add_plugin_decoration）
INDICATOR_PLUGIN = 8

# 标记 ID
MARKER_BOOKMARK = 0
MARKER_GIT_ADDED = 1
MARKER_GIT_MODIFIED = 2
MARKER_GIT_DELETED = 3
MARKER_BREAKPOINT = 4
MARKER_DEBUG_LINE = 5

# ============================================================
# 大文档模式阈值（性能优化）
# ============================================================
# 为什么需要（cProfile 实测，v2.2）：
#
#   * 2MB / 50 万行的 Python 文件，打开耗时 2.1s，其中
#     `setLexer` 占 **2.05s**（3 次调用，每次对整个文档重做样式），
#     小地图 `setText(全文)` 再占 **0.74s**；
#   * QScintilla 自己的 `setText` 只要 0.2~0.3s —— 高亮/缩略图才是大头。
#
# 超过阈值后：关闭语法高亮（保留纯文本），跳过小地图全文渲染。
# 这不影响编辑/保存/查找正确性，只损失"彩色显示"。
LARGE_DOC_LINES = 200_000  # 行数阈值
LARGE_DOC_BYTES = 8 * 1024 * 1024  # 字节阈值（8MB）

# 缩进彩虹线颜色
RAINBOW_COLORS = [
    QColor("#FF6B6B"),  # 红
    QColor("#FFA94D"),  # 橙
    QColor("#FFD43B"),  # 黄
    QColor("#69DB7C"),  # 绿
    QColor("#4DABF7"),  # 蓝
    QColor("#9775FA"),  # 紫
    QColor("#F783AC"),  # 粉
]

# 成对符号
PAIRS = {
    "(": ")",
    "[": "]",
    "{": "}",
    "<": ">",
    '"': '"',
    "'": "'",
    "`": "`",
}

# 反向映射（右符号 -> 左符号）
REVERSE_PAIRS = {v: k for k, v in PAIRS.items() if v != k}
REVERSE_PAIRS.update({")": "(", "]": "[", "}": "}", ">": "<"})

# 光标拖尾保留时长（秒）
CURSOR_TRAIL_DURATION = 0.2

# 默认字号
DEFAULT_FONT_SIZE = 12


# ============================================================
# 语法高亮：扩展名 -> QScintilla 词法器类名（P5）
# ============================================================
# 设计要点：
#   1. 这里只登记**类名字符串**，实例化时用 getattr(PyQt5.Qsci, 名字)
#      按名动态解析。不同 QScintilla 构建可能缺少某些词法器，动态
#      解析可优雅降级为 setLexer(None)（零高亮），绝不会因 import
#      一个不存在的名字而让整个模块导入失败。
#   2. 优先级（高 -> 低）：
#        a. 主窗口 _custom_lexers 插件注册表（按扩展名注册的工厂函数）
#        b. .log -> core.log_lexer.LogLexer（专用自定义词法器）
#        c. 本映射表（QScintilla 自带词法器）
#        d. 未登记扩展名 -> setLexer(None)，零高亮但不报错
#   3. 兜底说明：QScintilla 官方**没有** Go / Rust / TypeScript 词法器。
#      .go/.rs 用 QsciLexerCPP 近似高亮，.ts/.tsx 用 QsciLexerJavaScript
#      近似高亮（关键字着色大体正确，类型语法无法区分）。
#      汇编**不能**用 QsciLexerAsm（C++ 抽象类，实例化即 TypeError），
#      改用可实例化的 QsciLexerNASM；登记类名时请用
#      is_instantiable_lexer() 自查。
#   4. Markdown 只做语法高亮，不做实时预览联动。
#   5. core/editor.py 中另有一份历史副本（EditorProxy 内的同名逻辑）。
#      **本处是权威实现**，core 那份仅为兼容保留，修改请以这里为准。
_LEXER_GROUPS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    # Python
    ("QsciLexerPython", (".py", ".pyw", ".pyi")),
    # C / C++ / 类 C；.go / .rs 无官方词法器，用 CPP 兜底
    (
        "QsciLexerCPP",
        (
            ".c",
            ".h",
            ".cpp",
            ".cc",
            ".cxx",
            ".hpp",
            ".hxx",
            ".hh",
            ".ino",
            ".go",
            ".rs",
        ),
    ),
    # JSON（.jsonc/.json5 带注释，仍按 JSON 高亮）
    ("QsciLexerJSON", (".json", ".jsonc", ".json5")),
    # JavaScript / TypeScript（无 TS 词法器，用 JS 兜底）
    ("QsciLexerJavaScript", (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx")),
    # HTML / XML 系
    ("QsciLexerHTML", (".html", ".htm", ".xhtml")),
    ("QsciLexerXML", (".xml", ".svg", ".xsl", ".xslt", ".plist")),
    # CSS 及其方言
    ("QsciLexerCSS", (".css", ".scss", ".less")),
    # Markdown（仅高亮）
    ("QsciLexerMarkdown", (".md", ".markdown", ".mdown", ".mkd")),
    # YAML
    ("QsciLexerYAML", (".yml", ".yaml")),
    # SQL
    ("QsciLexerSQL", (".sql",)),
    # Shell 系
    ("QsciLexerBash", (".sh", ".bash", ".zsh", ".ksh")),
    # Windows 批处理
    ("QsciLexerBatch", (".bat", ".cmd")),
    # 其他主流语言
    ("QsciLexerJava", (".java",)),
    ("QsciLexerCSharp", (".cs",)),
    ("QsciLexerRuby", (".rb", ".rake", ".gemspec")),
    ("QsciLexerPerl", (".pl", ".pm", ".t")),
    ("QsciLexerLua", (".lua",)),
    ("QsciLexerTeX", (".tex", ".ltx", ".sty")),
    # 补丁 / 差异
    ("QsciLexerDiff", (".diff", ".patch")),
    # 配置文件
    ("QsciLexerProperties", (".ini", ".cfg", ".conf", ".properties", ".desktop")),
    # 构建系统
    ("QsciLexerCMake", (".cmake",)),
    ("QsciLexerMakefile", (".mk", ".mak", ".make")),
    # 汇编
    # 注意：**不能**用 QsciLexerAsm —— 它是 C++ 抽象类，实例化会抛
    # "represents a C++ abstract class and cannot be instantiated"，
    # 实测（本次 P5）会导致 .asm/.s 静默零高亮。
    # QsciLexerNASM / QsciLexerMASM 都是可实例化的具体类。
    ("QsciLexerNASM", (".asm", ".s")),
)

# 展开后的最终映射：扩展名（小写，含点）-> 词法器类名
LEXER_BY_EXTENSION: Dict[str, str] = {
    ext: lexer_name for lexer_name, extensions in _LEXER_GROUPS for ext in extensions
}


def resolve_lexer_class(lexer_name: Optional[str]):
    """
    按类名从 PyQt5.Qsci 动态解析词法器类。

    参数:
        lexer_name: 形如 "QsciLexerJSON" 的类名

    返回:
        词法器类；该类在本 QScintilla 构建中不存在时返回 None
    """
    if not lexer_name:
        return None
    return getattr(Qsci, lexer_name, None)


def is_instantiable_lexer(lexer_name: Optional[str]) -> bool:
    """
    判断某个 QScintilla 词法器是否**可以实例化**。

    背景（P5 实测踩坑）: QScintilla 里有些 QsciLexer* 是 **C++ 抽象类**
    （已实测 `QsciLexerAsm`、`QsciLexerCustom`）。`getattr` 能正常拿到
    类对象、`hasattr` 也为 True，但 `QsciLexerAsm()` 会抛
    "represents a C++ abstract class and cannot be instantiated" 的
    TypeError —— 映射表一旦登记这类名字，就会**静默退化成零高亮**。

    参数:
        lexer_name: 形如 "QsciLexerJSON" 的类名

    返回:
        True 表示可以实例化；类不存在、或是抽象类时返回 False
    """
    lexer_class = resolve_lexer_class(lexer_name)
    if lexer_class is None:
        return False
    try:
        lexer_class()
    except TypeError:
        # 抽象类，或构造函数签名不符
        return False
    except Exception:
        # 其它异常（例如极端环境下缺少 Qt 运行时）不判定为"不可实例化"，
        # 交给真正的创建流程去处理
        return True
    return True


def create_lexer_for_extension(ext: str, parent=None):
    """
    按扩展名创建 QScintilla 词法器实例。

    参数:
        ext: 扩展名（大小写不敏感，可带点也可不带点）
        parent: 词法器的 QObject 父对象（通常传编辑器自身，保证生命周期）

    返回:
        词法器实例；未登记的扩展名、本构建缺类、或该类是抽象类时返回 None
    """
    if not ext:
        return None
    if not ext.startswith("."):
        ext = "." + ext

    # v2.3：声明式语言包（Notepad++ UDL 等价物）优先于内置映射表。
    # 用户/插件投放 data/language_packs/*.qingcao-lang.json 即可加语言，
    # 无需写 Python 词法器类。
    try:
        from core.language_pack import get_pack_for_extension

        pack = get_pack_for_extension(ext)
        if pack is not None:
            from ui.generic_lexer import create_generic_lexer

            return create_generic_lexer(pack, parent)
    except Exception as e:
        print(f"[EditorWidget] 语言包加载失败({ext}): {e}")

    lexer_name = LEXER_BY_EXTENSION.get(ext.lower())
    if not is_instantiable_lexer(lexer_name):
        # 这里**显式**打印而不是静默返回 None：登记了不存在的类或
        # 抽象类（如 QsciLexerAsm）属于配置错误，必须看得见。
        if lexer_name:
            print(
                f"[EditorWidget] 词法器 {lexer_name} 不可实例化"
                f"（不存在或为 C++ 抽象类），{ext} 将零高亮"
            )
        return None

    lexer_class = resolve_lexer_class(lexer_name)
    try:
        return lexer_class(parent)
    except TypeError:
        # 极少数自定义词法器可能不接受 parent 参数
        pass
    except Exception as e:
        print(f"[EditorWidget] 创建词法器 {lexer_name} 失败: {e}")
        return None

    try:
        return lexer_class()
    except Exception as e:
        print(f"[EditorWidget] 创建词法器 {lexer_name} 失败: {e}")
        return None


# ============================================================
# 本地补全（P10）
# ============================================================
# core/local_completer.py 的 LocalCompleter 是纯本地实现
# （语言关键字 + 当前文件词频 + 全局词频 + 最近使用），此前完全未接线。
# 默认**开启**——它零依赖、不联网，属于"像真正的代码编辑器"的基础能力。
# 关闭方式: Preferences 里设 local_completion=False。
DEFAULT_LOCAL_COMPLETION = True
# 触发补全所需的最少前缀长度（与旧的 setAutoCompletionThreshold(2) 对齐）
COMPLETION_MIN_PREFIX = 2
# 单次最多给出的候选数
COMPLETION_MAX_ITEMS = 50
# 同一前缀的候选缓存有效期（秒）——避免同一前缀被反复重算
COMPLETION_CACHE_TTL = 0.5
# 重新索引文档词频的最小间隔（秒）——避免长文档每次按键全量扫描
COMPLETION_INDEX_MIN_INTERVAL = 0.75
# 候选缓存的最大条目数（超过则整体清空，避免无界增长）
COMPLETION_CACHE_MAX_ENTRIES = 128
# 扩展名 -> LocalCompleter.language_keywords 的语言键
# （未登记的扩展名用 ""，表示只给文档词/全局词，不硬塞别的语言的关键字）
COMPLETION_LANGUAGE_BY_EXT = {
    ".py": "python",
    ".pyw": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "javascript",
    ".tsx": "javascript",
}


# ============================================================
# 编辑器控件
# ============================================================


__all__ = [
    "COMPLETION_CACHE_MAX_ENTRIES",
    "COMPLETION_CACHE_TTL",
    "COMPLETION_INDEX_MIN_INTERVAL",
    "COMPLETION_LANGUAGE_BY_EXT",
    "COMPLETION_MAX_ITEMS",
    "COMPLETION_MIN_PREFIX",
    "CURSOR_TRAIL_DURATION",
    "DEFAULT_FONT_SIZE",
    "DEFAULT_LOCAL_COMPLETION",
    "INDICATOR_CURRENT_MATCH",
    "INDICATOR_CURSOR_TRAIL",
    "INDICATOR_LSP_ERROR",
    "INDICATOR_PLUGIN",
    "INDICATOR_SEARCH",
    "INDICATOR_SMART_HIGHLIGHT",
    "INDICATOR_SNIPPET",
    "LARGE_DOC_BYTES",
    "LARGE_DOC_LINES",
    "MARKER_BOOKMARK",
    "MARKER_BREAKPOINT",
    "MARKER_DEBUG_LINE",
    "MARKER_GIT_ADDED",
    "MARKER_GIT_DELETED",
    "MARKER_GIT_MODIFIED",
    "PAIRS",
    "RAINBOW_COLORS",
    "REVERSE_PAIRS",
    "create_lexer_for_extension",
    "is_instantiable_lexer",
    "resolve_lexer_class",
]


# v2.24：显式导出全部公共符号（供 Mixin 星号导入）
__all__ = [n for n in dir() if not n.startswith('__')]
