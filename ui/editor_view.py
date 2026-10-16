#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
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
from PyQt5.QtCore import QMimeData, QPoint, QRectF, Qt, QTimer, QUrl, pyqtSignal
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
from PyQt5.QtWidgets import QApplication, QMenu, QMessageBox

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

# 标记 ID
MARKER_BOOKMARK = 0
MARKER_GIT_ADDED = 1
MARKER_GIT_MODIFIED = 2
MARKER_GIT_DELETED = 3
MARKER_BREAKPOINT = 4
MARKER_DEBUG_LINE = 5

# 缩进彩虹线颜色
RAINBOW_COLORS = [
    QColor("#FF6B6B"),   # 红
    QColor("#FFA94D"),   # 橙
    QColor("#FFD43B"),   # 黄
    QColor("#69DB7C"),   # 绿
    QColor("#4DABF7"),   # 蓝
    QColor("#9775FA"),   # 紫
    QColor("#F783AC"),   # 粉
]

# 成对符号
PAIRS = {
    '(': ')',
    '[': ']',
    '{': '}',
    '<': '>',
    '"': '"',
    "'": "'",
    '`': '`',
}

# 反向映射（右符号 -> 左符号）
REVERSE_PAIRS = {v: k for k, v in PAIRS.items() if v != k}
REVERSE_PAIRS.update({')': '(', ']': '[', '}': '}', '>': '<'})

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
    ("QsciLexerCPP", (
        ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".hh",
        ".ino", ".go", ".rs",
    )),
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
    ext: lexer_name
    for lexer_name, extensions in _LEXER_GROUPS
    for ext in extensions
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
class EditorWidget(QsciScintilla):
    """
    编辑器视图控件。

    基于 QScintilla，提供：
    - 语法高亮（Python/C++/日志）
    - 代码折叠
    - 缩进彩虹线
    - 智能输入（括号、引号、缩进）
    - 书签标记
    - 多光标
    - 智能高亮
    - 拖放文件
    - 右键菜单

    信号:
        file_dropped(str): 文件被拖入（文件路径）
        focus_received(): 获得焦点
    """

    file_dropped = pyqtSignal(str)
    focus_received = pyqtSignal()

    def __init__(self, provider=None, prefs: Optional[Preferences] = None,
                 parent=None):
        """
        参数:
            provider: 内容提供者（可选）
            prefs: 偏好设置（可选）
            parent: 父控件
        """
        super().__init__(parent)

        # 偏好设置
        self.prefs = prefs or Preferences()

        # 内容提供者
        if provider is not None:
            # 显式传入的 provider（如打开文件时）
            self.prov = provider
        else:
            # 未指定：创建空的内存提供者，必须显式 open()
            # 否则 provider 状态为 CLOSED，_save_draft 时会报
            # "提供者未打开"
            self.prov = MemoryProvider()
            try:
                self.prov.open(initial_text="")
            except Exception as _e:
                print(f"[EditorWidget] 初始化 MemoryProvider 失败: {_e}")

        # 文档对象
        self.document = Document(provider=self.prov)

        # 编辑器代理
        self.proxy = EditorProxy(self, self.document)

        # 状态
        self._rainbow_enabled = self.prefs.get("indent_rainbow", False)
        self._cursor_trail_enabled = self.prefs.get("cursor_trail", False)
        self._smart_highlight_enabled = self.prefs.get("smart_highlight", True)
        self._cursor_trail_points: List[Tuple[int, float]] = []

        # P10: 本地补全状态（core/local_completer 的 LocalCompleter 是
        # 全局单例；这里把它接进编辑器补全路径，此前它零调用方）
        self._local_completer = get_local_completer()
        self._completion_enabled = bool(
            self.prefs.get("local_completion", DEFAULT_LOCAL_COMPLETION)
        )
        self._completion_min_prefix = max(
            COMPLETION_MIN_PREFIX,
            int(self.prefs.get("local_completion_min_prefix", COMPLETION_MIN_PREFIX)),
        )
        # 未保存缓冲区也有一个稳定的"文件键"，用于 LocalCompleter 的
        # file_words / recent_words 隔离（避免多标签页互相污染）。
        # 已保存的文件优先用真实路径，见 _completion_key()。
        self._completion_buffer_key = f"<buffer:{id(self)}>"
        self._completion_index_ts = 0.0
        self._completion_cache: Dict[str, Tuple[float, List[str]]] = {}

        # 配置
        self._configure()

        # 初始化指示器
        self._init_indicators()

        # 初始化标记
        self._init_markers()

        # 连接信号
        self._connect_signals()

        # TEDITOR: 应用当前主题（从 QSettings 读 theme_name）
        # main.py 的 load_theme() 只在启动时对 app 应用 QSS，
        # 但此时编辑器还不存在。新建/打开的 EditorWidget 需要
        # 主动应用当前主题，否则会用默认样式。
        self._apply_current_theme()

    def _apply_current_theme(self):
        """从 QSettings 读取当前主题并应用到自身"""
        try:
            from PyQt5.QtCore import QSettings

            from infrastructure.theme_loader import ThemeLoader

            settings = QSettings("QingCao", "Editor")
            theme_name = settings.value("theme_name", "", type=str)
            if not theme_name:
                return

            loader = ThemeLoader()
            theme = loader.load_by_name(theme_name)
            if theme is not None:
                loader.apply(self, theme)
        except Exception as e:
            print(f"[EditorWidget] 应用主题失败: {e}")

    # ========================================================
    # 配置
    # ========================================================
    def _configure(self):
        """配置编辑器基础属性"""
        # 编码
        self.setUtf8(True)

        # 字体
        try:
            font = self.prefs.build_font()
        except Exception:
            font = QFont("Consolas", DEFAULT_FONT_SIZE)
        self.setFont(font)
        self.setMarginsFont(font)

        # 边距（行号）
        self.setMarginType(0, QsciScintilla.NumberMargin)
        self.setMarginWidth(0, 50)

        # 断点/书签装订线（D3）
        # 修复：markerDefine 早就定义了圆点标记，但**没有任何边距显示
        # 它们**（原来只设了 margin 0 = 行号、margin 2 = 折叠），
        # 于是 markerAdd 出来的书签/断点全都看不见。
        # margin 1 紧贴行号右侧，正是"装订线"该在的位置。
        #
        # 为什么**不**把行号边距（margin 0）也设成可点：
        #   行号边距上已有"双击切换书签"（见 mouseDoubleClickEvent）。
        #   Qt 在**敏感边距**上会吞掉 mousePressEvent 并只发 marginClicked，
        #   于是双击加书签会顺带留下一个断点 —— 属于交互回归。
        #   因此断点单击只落在专用装订线上，行号区保持原样。
        self.setMarginType(1, QsciScintilla.SymbolMargin)
        self.setMarginWidth(1, 18)
        self.setMarginSensitivity(1, True)
        self.setMarginMarkerMask(
            1,
            (1 << MARKER_BOOKMARK) | (1 << MARKER_BREAKPOINT),
        )
        # Git 行标记是 Background 类型，直接画在文本区，不需要边距，
        # 因此不进 margin 1 的掩码（避免装订线出现大色块）。

        # 折叠边距
        self.setMarginType(2, QsciScintilla.SymbolMargin)
        self.setMarginWidth(2, 14)

        # 代码折叠
        try:
            self.setFolding(QsciScintilla.BoxedFoldStyle)
        except Exception:
            self.setFolding(QsciScintilla.PlainFoldStyle)

        # 折叠标记颜色
        self.setFoldMarginColors(QColor("#2d2d2d"), QColor("#2d2d2d"))

        # 缩进
        self.setAutoIndent(True)
        self.setIndentationsUseTabs(self.prefs.get("indent_use_tabs", False))
        self.setTabWidth(self.prefs.get("tab_width", 4))
        self.setIndentationWidth(self.prefs.get("tab_width", 4))
        self.setIndentationGuides(self.prefs.get("indent_guides", True))
        self.setBackspaceUnindents(
            self.prefs.get("indent_backspace_unindent", True)
        )
        self.setTabIndents(True)

        # 换行
        wrap_mode = self.prefs.get("word_wrap", False)
        if wrap_mode:
            self.setWrapMode(QsciScintilla.WrapWord)
        else:
            self.setWrapMode(QsciScintilla.WrapNone)

        # 光标
        self.setCaretLineVisible(
            self.prefs.get("show_current_line", True)
        )
        self.setCaretLineBackgroundColor(QColor("#f0f0f0"))
        self.setCaretWidth(self.prefs.get("caret_width", 1))

        # 括号匹配
        if self.prefs.get("show_matching_braces", True):
            self.setBraceMatching(QsciScintilla.SloppyBraceMatch)
            self.setMatchedBraceForegroundColor(QColor("#FFAA00"))
            self.setMatchedBraceBackgroundColor(QColor("#444400"))
        else:
            self.setBraceMatching(QsciScintilla.NoBraceMatch)

        # 空白字符显示
        if self.prefs.get("show_whitespace", False):
            self.setWhitespaceVisibility(QsciScintilla.WsVisible)
        else:
            self.setWhitespaceVisibility(QsciScintilla.WsInvisible)

        # 行尾符显示
        self.setEolVisibility(self.prefs.get("show_eol", False))

        # 光标位置可见
        self.setCursorPosition(0, 0)

        # 拖放
        self.setAcceptDrops(True)

        # 选择颜色
        try:
            self.setSelectionBackgroundColor(
                QColor(self.prefs.get("selection_color", "#264F78"))
            )
        except Exception:
            pass

        # 滚动
        self.setScrollWidth(1)
        self.setScrollWidthTracking(True)

        # 自动补全（P10: 改为由 LocalCompleter 提供候选，见 _setup_autocompletion）
        self._setup_autocompletion()

        # B: 禁用 QScintilla 内置 Ctrl+Z/Ctrl+Y 快捷键
        # 原因:
        #   EditorProxy 禁用了 Scintilla 内置 undo 栈，改用自己的
        #   undo_manager。但 QScintilla 默认仍响应 Ctrl+Z/Ctrl+Y
        #   按键，执行"内置 undo"（空操作），并吃掉按键 —— 导致
        #   主窗口菜单的撤销/重做快捷键收不到。
        # 解决:
        #   把 Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z 的内置绑定清除。
        try:
            from PyQt5.QtCore import Qt as _Qt
            for _key, _mod in [
                (_Qt.Key_Z, _Qt.ControlModifier),
                (_Qt.Key_Y, _Qt.ControlModifier),
                (_Qt.Key_Z, _Qt.ControlModifier | _Qt.ShiftModifier),
            ]:
                try:
                    self.SendScintilla(
                        QsciScintilla.SCI_CLEARCMDKEY,
                        _key + (_mod << 16),
                    )
                except Exception:
                    pass
        except Exception:
            pass

    def _init_indicators(self):
        """初始化指示器"""
        try:
            # 搜索高亮（黄色）
            self.indicatorDefine(
                QsciScintilla.INDIC_STRAIGHTBOX, INDICATOR_SEARCH
            )
            self.setIndicatorForegroundColor(
                QColor(255, 255, 0, 120), INDICATOR_SEARCH
            )
            self.setIndicatorOutlineColor(
                QColor(255, 200, 0), INDICATOR_SEARCH
            )

            # 当前匹配（橙色）
            self.indicatorDefine(
                QsciScintilla.INDIC_ROUNDBOX, INDICATOR_CURRENT_MATCH
            )
            self.setIndicatorForegroundColor(
                QColor(255, 128, 0, 180), INDICATOR_CURRENT_MATCH
            )

            # LSP 错误（红色波浪线）
            self.indicatorDefine(
                QsciScintilla.INDIC_SQUIGGLE, INDICATOR_LSP_ERROR
            )
            self.setIndicatorForegroundColor(
                QColor(255, 0, 0), INDICATOR_LSP_ERROR
            )

            # 代码片段占位符（蓝色）
            self.indicatorDefine(
                QsciScintilla.INDIC_STRAIGHTBOX, INDICATOR_SNIPPET
            )
            self.setIndicatorForegroundColor(
                QColor(0, 120, 215, 100), INDICATOR_SNIPPET
            )

            # 光标拖尾（淡黄）
            self.indicatorDefine(
                QsciScintilla.INDIC_STRAIGHTBOX, INDICATOR_CURSOR_TRAIL
            )
            self.setIndicatorForegroundColor(
                QColor(255, 255, 0, 80), INDICATOR_CURSOR_TRAIL
            )

            # 智能高亮（灰）
            self.indicatorDefine(
                QsciScintilla.INDIC_STRAIGHTBOX, INDICATOR_SMART_HIGHLIGHT
            )
            self.setIndicatorForegroundColor(
                QColor(100, 100, 100, 60), INDICATOR_SMART_HIGHLIGHT
            )

        except Exception as e:
            print(f"[EditorWidget] 初始化指示器失败: {e}")

    def _init_markers(self):
        """初始化标记"""
        try:
            # 书签（圆形）
            self.markerDefine(QsciScintilla.Circle, MARKER_BOOKMARK)
            self.setMarkerBackgroundColor(QColor("#007acc"), MARKER_BOOKMARK)
            self.setMarkerForegroundColor(QColor("#ffffff"), MARKER_BOOKMARK)

            # Git 标记（背景色）
            self.markerDefine(QsciScintilla.Background, MARKER_GIT_ADDED)
            self.setMarkerBackgroundColor(
                QColor(0, 255, 0, 40), MARKER_GIT_ADDED
            )

            self.markerDefine(QsciScintilla.Background, MARKER_GIT_MODIFIED)
            self.setMarkerBackgroundColor(
                QColor(0, 120, 215, 40), MARKER_GIT_MODIFIED
            )

            self.markerDefine(QsciScintilla.Background, MARKER_GIT_DELETED)
            self.setMarkerBackgroundColor(
                QColor(255, 0, 0, 40), MARKER_GIT_DELETED
            )

            # 断点（红圆）
            self.markerDefine(QsciScintilla.Circle, MARKER_BREAKPOINT)
            self.setMarkerBackgroundColor(
                QColor("#ff0000"), MARKER_BREAKPOINT
            )

            # 调试器当前停住的行（D3）：背景高亮。
            # Background 类型直接画在文本区，不依赖任何边距宽度。
            self.markerDefine(QsciScintilla.Background, MARKER_DEBUG_LINE)
            self.setMarkerBackgroundColor(
                QColor("#ffcc00"), MARKER_DEBUG_LINE
            )

        except Exception as e:
            print(f"[EditorWidget] 初始化标记失败: {e}")

    def _connect_signals(self):
        """连接内部信号"""
        try:
            self.cursorPositionChanged.connect(self._on_cursor_moved)
            self.SCN_CHARADDED.connect(self._on_char_added)
        except Exception:
            pass

        # D3: 装订线（行号 margin 0 / 断点 margin 1）单击切换断点
        try:
            self.marginClicked.connect(self._on_margin_clicked)
        except Exception:
            pass

        # P10: 用户"接受"一个补全项后记录使用，LocalCompleter 的
        # 词频排序 / 最近使用才有意义。
        # 优先接 SCN_AUTOCCOMPLETED（Scintilla 4.1+ 专门表示"完成插入"），
        # 老版本回退到 SCN_AUTOCSELECTION；两者都缺则静默跳过。
        try:
            self.SCN_AUTOCCOMPLETED.connect(self._on_completion_accepted)
        except Exception:
            try:
                self.SCN_AUTOCSELECTION.connect(self._on_completion_accepted)
            except Exception:
                pass

    # ========================================================
    # 本地补全（P10: 接线 core/local_completer.LocalCompleter）
    # ========================================================
    def _setup_autocompletion(self):
        """
        配置自动补全，并接管候选来源。

        P10 之前:
            setAutoCompletionSource(AcsAll) —— 走 QScintilla 内置弹窗，
            只补"当前文档里出现过的单词"，没有语言关键字、没有词频排序，
            且 core/local_completer.LocalCompleter **完全未被调用**。

        P10 之后:
            关闭 QScintilla 内置弹窗（AcsNone），改由本类在
            SCN_CHARADDED / Ctrl+Space 时用 LocalCompleter 取候选，
            再经 SCI_AUTOCSHOW 弹出（与 core/editor.py 的 LSP 补全
            使用同一条 Scintilla 通道）。
            "文档词补全"能力没有丢：LocalCompleter 的 file_words /
            word_freq 就是文档词来源，见 _sync_completion_words。

        不受影响的行为: 括号/引号自动闭合、智能缩进、折叠等与
        补全无关的 QScintilla 行为一律未改动。
        """
        try:
            # AcsNone: 内置弹窗关闭，避免与自定义候选在同一按键上互相覆盖
            self.setAutoCompletionSource(QsciScintilla.AcsNone)
        except Exception:
            pass
        try:
            # -1 = 不使用内置阈值；触发门槛由 _completion_min_prefix 控制
            self.setAutoCompletionThreshold(-1)
        except Exception:
            pass
        try:
            self.setAutoCompletionCaseSensitivity(False)
            self.setAutoCompletionReplaceWord(False)
        except Exception:
            pass

    def _completion_language(self) -> str:
        """把当前文件扩展名映射到 LocalCompleter 的语言键（未知则空串）"""
        ext = os.path.splitext(self._completion_key())[1].lower()
        return COMPLETION_LANGUAGE_BY_EXT.get(ext, "")

    def _completion_key(self) -> str:
        """
        当前缓冲区的词频键。

        已保存文件用真实路径（这样 LocalCompleter 的 file_words
        能与磁盘文件对应），未保存缓冲区用稳定的实例内键。
        """
        try:
            filepath = getattr(self.document, "filepath", "") or ""
        except Exception:
            filepath = ""
        return filepath or self._completion_buffer_key

    def _current_prefix(self) -> Tuple[str, int]:
        """
        取光标左侧的标识符前缀。

        返回:
            (前缀, 前缀的 UTF-8 字节长度)；光标不在标识符末尾时返回 ("", 0)

        说明: 本文件统一按**字节偏移**处理 Scintilla 位置
        （见 _smart_home / _wrap_selection 的修复记录），这里同样用
        SCI_GETCURRENTPOS 减行首位置得到字节偏移，避免中英文混排错位。
        """
        try:
            pos = self.SendScintilla(QsciScintilla.SCI_GETCURRENTPOS)
            line = self.SendScintilla(QsciScintilla.SCI_LINEFROMPOSITION, pos)
            line_start = self.SendScintilla(
                QsciScintilla.SCI_POSITIONFROMLINE, line
            )
            line_text = self.text(line)
            offset = max(0, pos - line_start)
            head = line_text.encode("utf-8")[:offset].decode("utf-8", "ignore")
        except Exception:
            return "", 0

        match = re.search(r"[A-Za-z_][A-Za-z0-9_]*\Z", head)
        if match is None:
            return "", 0
        prefix = match.group(0)
        return prefix, len(prefix.encode("utf-8"))

    def _sync_completion_words(self) -> None:
        """
        把当前文档内容同步给 LocalCompleter。

        性能保护（P10）: 全量正则扫描文档词频在长文档上有成本，
        因此按 COMPLETION_INDEX_MIN_INTERVAL 节流；候选结果本身
        另有 COMPLETION_CACHE_TTL 前缀缓存。
        """
        now = time.time()
        if (now - self._completion_index_ts) < COMPLETION_INDEX_MIN_INTERVAL:
            return
        try:
            text = self.text()
        except Exception:
            return
        try:
            self._local_completer.update_from_file(self._completion_key(), text)
        except Exception as e:
            print(f"[EditorWidget] 更新补全词频失败: {e}")
            return
        self._completion_index_ts = now
        self._completion_cache.clear()

    def local_completions(self, prefix: str) -> List[str]:
        """
        用 LocalCompleter 计算候选词（公开方法，便于测试与插件复用）。

        参数:
            prefix: 已输入的前缀

        返回:
            候选词列表，排序为: 最近使用 -> 语言关键字 ->
            当前文件词频 -> 全局词频
        """
        if not self._completion_enabled:
            return []
        if not prefix or len(prefix) < self._completion_min_prefix:
            return []

        self._sync_completion_words()
        try:
            items = self._local_completer.get_completions(
                prefix,
                filepath=self._completion_key(),
                language=self._completion_language(),
                limit=COMPLETION_MAX_ITEMS,
            )
        except Exception as e:
            print(f"[EditorWidget] 本地补全计算失败: {e}")
            return []
        return [word for word, _source in items]

    def trigger_local_completion(self, force: bool = False) -> List[str]:
        """
        按当前前缀弹出本地补全列表。

        参数:
            force: True 时忽略前缀长度门槛（供 Ctrl+Space 使用）

        返回:
            本次实际使用的候选词列表（可能来自前缀缓存）
        """
        if not self._completion_enabled:
            return []

        prefix, prefix_bytes = self._current_prefix()
        if not prefix:
            return []
        if not force and len(prefix) < self._completion_min_prefix:
            return []

        now = time.time()
        cached = self._completion_cache.get(prefix)
        if cached is not None and (now - cached[0]) < COMPLETION_CACHE_TTL:
            words = list(cached[1])
        else:
            words = self.local_completions(prefix)
            self._completion_cache[prefix] = (now, list(words))
            if len(self._completion_cache) > COMPLETION_CACHE_MAX_ENTRIES:
                self._completion_cache.clear()

        if not words:
            return []

        try:
            self.SendScintilla(
                QsciScintilla.SCI_AUTOCSHOW,
                prefix_bytes,
                " ".join(words).encode("utf-8"),
            )
        except Exception as e:
            print(f"[EditorWidget] 弹出本地补全失败: {e}")
        return words

    def _on_completion_accepted(self, *args):
        """
        补全项被用户接受后的回调（P10）。

        SCN_AUTOCCOMPLETED / SCN_AUTOCSELECTION 的第一个参数是选中的
        词（sip 里是 str，个别版本是 bytes）；这里两种都兼容。
        """
        word = ""
        for arg in args:
            if isinstance(arg, str) and arg:
                word = arg
                break
            if isinstance(arg, (bytes, bytearray)):
                text = bytes(arg).decode("utf-8", "ignore")
                if text:
                    word = text
                    break
        if not word:
            return
        try:
            self._local_completer.record_used(word)
        except Exception as e:
            print(f"[EditorWidget] 记录补全使用失败: {e}")

    # ========================================================
    # 语法高亮
    # ========================================================
    def set_lexer_by_filename(self, filepath: Optional[str]):
        """
        根据文件扩展名设置词法器。

        优先级（高 -> 低），与模块级 LEXER_BY_EXTENSION 的注释一致：
            1. 主窗口 _custom_lexers 插件注册表（插件注册的优先）
            2. .log -> core.log_lexer.LogLexer（专用词法器）
            3. 内置扩展名映射表（LEXER_BY_EXTENSION）
            4. 无匹配 / 本构建缺该词法器 -> setLexer(None)（零高亮，不报错）

        说明：core/editor.py 中另有一份历史副本，**本处为权威实现**。

        参数:
            filepath: 文件路径（None / 空字符串表示清除词法器）
        """
        if not filepath:
            self.set_lexer(None)
            return

        ext = os.path.splitext(filepath)[1].lower()

        # 1) 插件注册的自定义词法器优先
        #    app/plugins.py 会往主窗口的 _custom_lexers 里按扩展名
        #    注册工厂函数；此处对所有扩展名都先查注册表。
        try:
            custom = getattr(self.window(), '_custom_lexers', None)
            factory = custom.get(ext) if isinstance(custom, dict) else None
            if factory is not None:
                lexer = factory()
                if lexer is not None:
                    self.set_lexer(lexer)
                    return
        except Exception as e:
            print(f"[EditorWidget] 自定义词法器创建失败({ext}): {e}")

        # 2) .log 专用词法器
        if ext == '.log':
            try:
                from core.log_lexer import LogLexer
                self.set_lexer(LogLexer(self))
            except Exception as e:
                print(f"[EditorWidget] 日志词法器加载失败: {e}")
                self.set_lexer(None)
            return

        # 3) 内置映射表；缺词法器时 create_lexer_for_extension 返回 None，
        #    由 set_lexer(None) 完成"零高亮"降级。
        try:
            self.set_lexer(create_lexer_for_extension(ext, self))
        except Exception as e:
            print(f"[EditorWidget] 设置词法器失败({ext}): {e}")
            self.set_lexer(None)

    def set_lexer(self, lexer):
        """重写，同时设置字体（并保证词法器生命周期）

        生命周期说明（P5 实测发现）：
            没有 QObject parent 的词法器在 Python 侧唯一的引用消失后
            会被回收，而 Scintilla 只持有**裸指针**，于是
            `self.lexer()` 变成 None（插件工厂返回的词法器正是这种）。
            这里对无 parent 的词法器统一 `setParent(self)`，
            让编辑器持有它 —— 内置路径虽然已经传了 parent，
            插件/外部传入的路径也一并兜住。
        """
        if lexer is not None:
            try:
                if lexer.parent() is None:
                    lexer.setParent(self)
            except Exception:
                pass

        super().setLexer(lexer)
        if lexer:
            try:
                lexer.setDefaultFont(self.font())
            except Exception:
                pass

    # ========================================================
    # 按键处理
    # ========================================================
    def keyPressEvent(self, event: QKeyEvent):
        """
        按键事件处理。

        智能处理:
        - 括号/引号自动包裹选区
        - 右括号/引号跳过
        - Tab/Shift+Tab 缩进
        - Home 键智能跳转
        - Ctrl+Backspace 按词删除
        - Backspace 删除成对符号
        - Esc 清除多光标
        - 代码片段触发
        - F9 切换断点（D3）
        """
        # D3: F9 切换当前行断点。
        # 刻意**放在 Vim 模式之前**，且刻意**不注册全局 QShortcut**：
        #   * 多标签场景下，每个编辑器各有一个全局 QShortcut 会造成
        #     Qt 的 ambiguous shortcut（P8-1 的教训）；
        #   * 放在 keyPressEvent 里天然只作用于**获得焦点的**编辑器。
        if event.key() == Qt.Key_F9 and not event.modifiers():
            self._toggle_breakpoint_at_line(
                self.getCursorPosition()[0]
            )
            event.accept()
            return

        # Vim 模式：优先让 VimMode 处理
        # （VimMode.handle_key 返回 True 表示已消化，直接 return）
        vim = getattr(self, '_vim_mode', None)
        if vim is not None and getattr(vim, 'enabled', False):
            try:
                if vim.handle_key(event):
                    return
            except Exception as e:
                print(f"[EditorWidget] VimMode 处理失败: {e}")

        key = event.key()
        text = event.text()
        modifiers = event.modifiers()

        # Esc：清除多光标
        if key == Qt.Key_Escape:
            if self.SendScintilla(QsciScintilla.SCI_GETSELECTIONS) > 1:
                self.proxy.clear_multi_cursors()
                return

        # Ctrl+Space：强制弹出本地补全（P10）
        if key == Qt.Key_Space and modifiers == Qt.ControlModifier:
            if self.trigger_local_completion(force=True):
                return

        # 括号/引号包裹选区
        if text in PAIRS and self.hasSelectedText():
            self._wrap_selection(text)
            return

        # 右括号/引号跳过
        if text in REVERSE_PAIRS and not modifiers:
            if self._try_skip_close(text):
                return

        # Tab 键
        if key == Qt.Key_Tab and not modifiers:
            if self._handle_tab():
                return
            # 默认插入 Tab
            self.SendScintilla(QsciScintilla.SCI_TAB)
            return

        # Shift+Tab 反缩进
        if key == Qt.Key_Backtab or (key == Qt.Key_Tab and modifiers == Qt.ShiftModifier):
            self.SendScintilla(QsciScintilla.SCI_BACKTAB)
            return

        # Home 键智能跳转
        if key == Qt.Key_Home and not modifiers:
            self._smart_home()
            return

        # Ctrl+Backspace 按词删除
        if key == Qt.Key_Backspace and modifiers == Qt.ControlModifier:
            self._delete_word_left()
            return

        # Backspace 删除成对符号
        if key == Qt.Key_Backspace and not modifiers:
            if self._try_delete_pair():
                return

        # 默认处理
        super().keyPressEvent(event)

    def _wrap_selection(self, open_char: str):
        """
        用成对符号包裹选区。

        修复说明（P1-1）:
            - QScintilla 在 UTF-8 模式下位置为字节偏移，
              而 Python str 的 len() 是字符数，两者对中文不一致。
            - 这里使用 encode('utf-8') 后的字节长度重新计算选区。
        """
        close_char = PAIRS[open_char]

        sel_start = self.SendScintilla(QsciScintilla.SCI_GETSELECTIONSTART)
        sel_end = self.SendScintilla(QsciScintilla.SCI_GETSELECTIONEND)
        selected = self.selectedText()

        # 构建包裹后的文本
        wrapped = open_char + selected + close_char

        # 替换
        self.SendScintilla(
            QsciScintilla.SCI_REPLACESEL, wrapped.encode('utf-8')
        )

        # 重新选中原内容（跳过左右符号）
        # 注意：QScintilla 位置是字节偏移，必须用 encode 后的长度
        open_len = len(open_char.encode('utf-8'))
        sel_len = len(selected.encode('utf-8'))

        new_start = sel_start + open_len
        new_end = new_start + sel_len
        self.SendScintilla(QsciScintilla.SCI_SETSELECTIONSTART, new_start)
        self.SendScintilla(QsciScintilla.SCI_SETSELECTIONEND, new_end)

    def _try_skip_close(self, close_char: str) -> bool:
        """尝试跳过右符号"""
        pos = self.SendScintilla(QsciScintilla.SCI_GETCURRENTPOS)
        length = self.SendScintilla(QsciScintilla.SCI_GETLENGTH)

        if pos >= length:
            return False

        next_char = chr(self.SendScintilla(QsciScintilla.SCI_GETCHARAT, pos))

        if next_char == close_char:
            self.SendScintilla(QsciScintilla.SCI_GOTOPOS, pos + 1)
            return True

        return False

    def _handle_tab(self) -> bool:
        """
        处理 Tab 键。

        返回:
            True 表示已处理，False 表示使用默认行为
        """
        # 有选区时缩进所有行
        if self.hasSelectedText():
            self.SendScintilla(QsciScintilla.SCI_TAB)
            return True

        # 无选区，检查代码片段触发
        line, col = self.getCursorPosition()
        line_text = self.text(line)

        before = line_text[:col]
        word = ""
        for i in range(len(before) - 1, -1, -1):
            ch = before[i]
            if ch.isalnum() or ch == '_':
                word = ch + word
            else:
                break

        if not word:
            return False

        # 修复说明（P1-4）: 优先查询用户片段 SnippetManager
        try:
            from core.snippets import get_snippet_manager
            mgr = get_snippet_manager()
            snippet = mgr.get(word)
            if snippet:
                body = snippet.body
                if isinstance(body, list):
                    body = '\n'.join(body)
                if body:
                    word_len_bytes = len(word.encode('utf-8'))
                    cur = self.SendScintilla(
                        QsciScintilla.SCI_GETCURRENTPOS
                    )
                    self.SendScintilla(
                        QsciScintilla.SCI_SETSELECTIONSTART,
                        cur - word_len_bytes
                    )
                    self.SendScintilla(
                        QsciScintilla.SCI_SETSELECTIONEND, cur
                    )
                    self.SendScintilla(
                        QsciScintilla.SCI_REPLACESEL,
                        body.encode('utf-8')
                    )
                    return True
        except Exception as e:
            print(f"[EditorWidget] SnippetManager 触发失败: {e}")

        # 回退到内置片段
        if word in self.proxy.SNIPPETS:
            try:
                self.proxy.expand_snippet(word)
                return True
            except Exception:
                pass

        return False

    def _smart_home(self):
        """
        Home 键智能循环跳转。

        修复说明（P1-2）:
            - 原实现中 `line_start + indent` 直接把字符长度当作
              字节偏移，遇到含 tab 或全角空格的行时位置会有偏差。
            - 修复为使用行首缩进部分的 UTF-8 字节长度。
        """
        line, col = self.getCursorPosition()
        line_text = self.text(line)

        # 计算行首非空白位置（字符数）
        stripped = line_text.lstrip()
        indent = len(line_text) - len(stripped)

        # 获取行首位置（字节偏移）
        line_start = self.SendScintilla(
            QsciScintilla.SCI_POSITIONFROMLINE, line
        )

        # 计算行首缩进的字节长度
        indent_bytes = len(line_text[:indent].encode('utf-8'))

        # P1-B4: col 是字节偏移，必须与 indent_bytes 比较（而非字符数 indent）
        # 否则全角空格（U+3000，UTF-8 下 3 字节）行为异常
        if col > indent_bytes:
            # 跳到行首非空白
            target = line_start + indent_bytes
        elif col == indent_bytes and indent_bytes > 0:
            # 跳到绝对行首
            target = line_start
        elif col == 0:
            # 循环回到行首非空白
            target = line_start + indent_bytes
        else:
            # 默认跳到行首
            target = line_start

        self.SendScintilla(QsciScintilla.SCI_GOTOPOS, target)

    def _delete_word_left(self):
        """按词删除（向左）"""
        pos = self.SendScintilla(QsciScintilla.SCI_GETCURRENTPOS)

        if pos <= 0:
            return

        # 使用 Scintilla 内置的按词删除
        # SCI_DELWORDLEFT 会删除到前一个词边界
        start = self.SendScintilla(
            QsciScintilla.SCI_WORDSTARTPOSITION, pos, True
        )

        if start < pos:
            self.SendScintilla(
                QsciScintilla.SCI_DELETERANGE, start, pos - start
            )
        else:
            # 回退到删除单个字符
            self.SendScintilla(QsciScintilla.SCI_DELETEBACK)

    def _try_delete_pair(self) -> bool:
        """
        尝试删除成对符号。

        修复说明（P1-3）:
            - SCI_GETCHARAT 返回的是字节值（0-255）。
              若光标处是中文字符的某个字节，chr() 会返回奇怪字符，
              极少数情况下可能恰好与括号字符相同。
            - 这里增加 ASCII 范围判断（0x20 < byte < 0x7F），
              只在纯 ASCII 括号场景下处理。
        """
        pos = self.SendScintilla(QsciScintilla.SCI_GETCURRENTPOS)

        if pos <= 0:
            return False

        length = self.SendScintilla(QsciScintilla.SCI_GETLENGTH)

        # 获取光标前后字符的字节值
        prev_byte = self.SendScintilla(QsciScintilla.SCI_GETCHARAT, pos - 1)

        if pos >= length:
            return False

        next_byte = self.SendScintilla(QsciScintilla.SCI_GETCHARAT, pos)

        # 只处理纯 ASCII 可打印字符
        if not (0x20 < prev_byte < 0x7F) or not (0x20 < next_byte < 0x7F):
            return False

        prev_char = chr(prev_byte)
        next_char = chr(next_byte)

        # 检查是否为成对符号
        if prev_char in PAIRS and PAIRS[prev_char] == next_char:
            # 同时删除两个字符
            self.SendScintilla(
                QsciScintilla.SCI_DELETERANGE, pos - 1, 2
            )
            return True

        return False

    # ========================================================
    # 字符输入回调
    # ========================================================
    def _on_char_added(self, char_code: int):
        """字符输入后的回调

        P1-4: 引号自动闭合 + 尊重偏好

        原实现用 `if char != close_char` 跳过所有引号（因为
        PAIRS['"'] == '"'），导致：
          - 输入 " 不会自动补 "
          - 而偏好设置里 auto_close_quotes 是打开的

        新实现：
          - 引号也自动闭合
          - 尊重 auto_close_brackets / auto_close_quotes 偏好
          - 引号闭合前检查前一个字符，避免在 don't 里误闭合
        """
        try:
            char = chr(char_code)

            # P10: 输入标识符字符后自动弹出本地补全
            # （关键字 + 文档词 + 词频排序，均来自 LocalCompleter）
            if char.isascii() and (char.isalnum() or char == "_"):
                self.trigger_local_completion()

            if char not in PAIRS:
                return
            if self.hasSelectedText():
                return

            close_char = PAIRS[char]

            if char == close_char:
                # 引号场景
                if not self.prefs.get("auto_close_quotes", True):
                    return
                # 前面是标识符字符时不闭合（如 don't）
                pos = self.SendScintilla(
                    QsciScintilla.SCI_GETCURRENTPOS
                )
                if pos >= 2:
                    prev_byte = self.SendScintilla(
                        QsciScintilla.SCI_GETCHARAT, pos - 2
                    )
                    if 0x20 < prev_byte < 0x7F:
                        prev_char = chr(prev_byte)
                        if prev_char.isalnum() or prev_char == '_':
                            return
            else:
                # 括号场景
                if not self.prefs.get("auto_close_brackets", True):
                    return

            # 插入闭合符号
            pos = self.SendScintilla(QsciScintilla.SCI_GETCURRENTPOS)
            self.SendScintilla(
                QsciScintilla.SCI_INSERTTEXT, pos,
                close_char.encode('utf-8')
            )
            # 光标保持在原位置
            self.SendScintilla(QsciScintilla.SCI_GOTOPOS, pos)
        except Exception:
            pass

    # ========================================================
    # 光标与拖尾
    # ========================================================
    def _on_cursor_moved(self, line: int, col: int):
        """光标移动回调"""
        # 光标拖尾
        if self._cursor_trail_enabled:
            self._update_cursor_trail()

    def _update_cursor_trail(self):
        """更新光标拖尾"""
        try:
            pos = self.SendScintilla(QsciScintilla.SCI_GETCURRENTPOS)
            now = time.time()

            self._cursor_trail_points.append((pos, now))

            # 清除旧指示器
            length = self.SendScintilla(QsciScintilla.SCI_GETLENGTH)
            self.SendScintilla(
                QsciScintilla.SCI_SETINDICATORCURRENT, INDICATOR_CURSOR_TRAIL
            )
            self.SendScintilla(
                QsciScintilla.SCI_INDICATORCLEARRANGE, 0, length
            )

            # 绘制新拖尾
            valid = []
            for p, t in self._cursor_trail_points:
                if now - t < CURSOR_TRAIL_DURATION:
                    self.SendScintilla(
                        QsciScintilla.SCI_INDICATORFILLRANGE, p, 1
                    )
                    valid.append((p, t))
            self._cursor_trail_points = valid

        except Exception:
            pass

    # ========================================================
    # 缩进彩虹线
    # ========================================================
    def set_rainbow_enabled(self, enabled: bool):
        """启用/禁用缩进彩虹线"""
        self._rainbow_enabled = enabled
        self.viewport().update()

    def paintEvent(self, event):
        """
        重写绘制事件，绘制彩虹线。

        性能优化说明（P2-2）:
            - 缓存行高，避免每级缩进都查询 SCI_TEXTHEIGHT。
            - 只在缩进 > 0 的行上绘制，跳过空白行。
            - 使用局部变量减少属性查找。
            - 一次性读取可见行范围，避免在循环中重复计算。
        """
        super().paintEvent(event)

        if not self._rainbow_enabled:
            return

        try:
            painter = QPainter(self.viewport())

            # 获取可见行范围
            first_visible = self.SendScintilla(
                QsciScintilla.SCI_GETFIRSTVISIBLELINE
            )
            lines_on_screen = self.SendScintilla(
                QsciScintilla.SCI_LINESONSCREEN
            )

            tab_width = max(1, self.tabWidth())

            for i in range(lines_on_screen + 1):
                line = first_visible + i

                try:
                    line_text = self.text(line)
                except Exception:
                    continue

                if not line_text:
                    continue

                # 计算缩进级别
                stripped = line_text.lstrip()
                indent = len(line_text) - len(stripped)

                if indent == 0:
                    continue

                level = indent // tab_width
                if level <= 0:
                    continue

                # 缓存行高（每次循环只查一次）
                line_height = self.SendScintilla(
                    QsciScintilla.SCI_TEXTHEIGHT, line
                )

                # 行起始字节位置
                line_start = self.SendScintilla(
                    QsciScintilla.SCI_POSITIONFROMLINE, line
                )

                # 绘制每一层的彩虹线
                for lv in range(level):
                    color = RAINBOW_COLORS[lv % len(RAINBOW_COLORS)]
                    painter.setPen(QPen(color, 1))

                    # 计算 x 坐标
                    char_pos = lv * tab_width
                    if char_pos >= len(line_text):
                        continue

                    pos = line_start + char_pos

                    x = self.SendScintilla(
                        QsciScintilla.SCI_POINTXFROMPOSITION, 0, pos
                    )
                    y = self.SendScintilla(
                        QsciScintilla.SCI_POINTYFROMPOSITION, 0, pos
                    )

                    if x < 0 or y < 0:
                        continue

                    painter.drawLine(x, y, x, y + line_height)

            painter.end()

        except Exception:
            pass

    # ========================================================
    # 鼠标事件
    # ========================================================
    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下事件"""
        # Ctrl+点击：添加多光标
        if event.modifiers() == Qt.ControlModifier and event.button() == Qt.LeftButton:
            pos = self.SendScintilla(
                QsciScintilla.SCI_POSITIONFROMPOINT,
                event.pos().x(), event.pos().y()
            )
            if pos >= 0:
                self.proxy.add_cursor_at(pos)
                event.accept()
                return

        # Alt+点击：切换书签
        if event.modifiers() == Qt.AltModifier and event.button() == Qt.LeftButton:
            pos = self.SendScintilla(
                QsciScintilla.SCI_POSITIONFROMPOINT,
                event.pos().x(), event.pos().y()
            )
            if pos >= 0:
                line = self.SendScintilla(
                    QsciScintilla.SCI_LINEFROMPOSITION, pos
                )
                self._toggle_bookmark_at_line(line)
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """双击事件"""
        # 双击行号边距：切换书签
        if event.pos().x() < 50:
            line, _ = self.getCursorPosition()
            self._toggle_bookmark_at_line(line)
            event.accept()
            return

        super().mouseDoubleClickEvent(event)

    def _toggle_bookmark_at_line(self, line: int):
        """在指定行切换书签"""
        try:
            if self.markersAtLine(line) & (1 << MARKER_BOOKMARK):
                self.markerDelete(line, MARKER_BOOKMARK)
                self.document.remove_bookmark(line)
            else:
                self.markerAdd(line, MARKER_BOOKMARK)
                self.document.add_bookmark(line)
        except Exception:
            pass

    # ========================================================
    # 断点（D3）
    # ========================================================
    def _on_margin_clicked(self, margin: int, line: int, modifiers):
        """装订线单击 → 切换断点。

        只有 margin 1（紧贴行号右侧的专用断点装订线）会切换断点。
        行号边距（margin 0）**刻意保持不可点**：那里已有"双击切换
        书签"的交互，而 Qt 在敏感边距上会吞掉 mousePressEvent，
        两者叠加会让"双击加书签"顺带留下一个断点。

        另外两个等价入口：F9（编辑器内，见 keyPressEvent）与右键菜单。
        """
        try:
            if margin == 1:
                self._toggle_breakpoint_at_line(line)
                return True
        except Exception as e:
            print(f"[EditorWidget] 切换断点失败: {e}")
        return False

    def _toggle_breakpoint_at_line(self, line: int):
        """在指定行切换断点标记（与 `_toggle_bookmark_at_line` 对称）。

        行号越界（空文件 / 行号超过文件末尾）时返回 **False 且不做任何
        修改**：QScintilla 的 `markerAdd()` 对越界行是**静默失败**的，
        若此处无条件 `return True`，调用方会以为断点设上了而实际没有
        —— 返回值必须与实际效果一致。
        """
        try:
            line = int(line)
            if line < 0 or line >= max(1, int(self.lines())):
                return False
            if self.markersAtLine(line) & (1 << MARKER_BREAKPOINT):
                self.markerDelete(line, MARKER_BREAKPOINT)
            else:
                self.markerAdd(line, MARKER_BREAKPOINT)
            # 通知代理（它会再广播 breakpoints_changed 给调试器）
            try:
                proxy = getattr(self, 'proxy', None)
                if proxy is not None:
                    proxy._emit_breakpoints_changed()
            except Exception:
                pass
            return True
        except Exception as e:
            print(f"[EditorWidget] 切换断点失败: {e}")
            return False

    def get_breakpoints(self):
        """返回已设断点的行号列表（升序）。"""
        try:
            total = self.lines()
            return [
                line for line in range(total)
                if self.markersAtLine(line) & (1 << MARKER_BREAKPOINT)
            ]
        except Exception as e:
            print(f"[EditorWidget] 读取断点失败: {e}")
            return []

    def clear_breakpoints(self):
        """清除本编辑器的所有断点，返回清除数量。"""
        try:
            lines = self.get_breakpoints()
            self.markerDeleteAll(MARKER_BREAKPOINT)
            try:
                proxy = getattr(self, 'proxy', None)
                if proxy is not None:
                    proxy._emit_breakpoints_changed()
            except Exception:
                pass
            return len(lines)
        except Exception as e:
            print(f"[EditorWidget] 清除断点失败: {e}")
            return 0

    def highlight_debug_line(self, line: int):
        """高亮调试器当前停住的行（D3）。"""
        try:
            self.markerDeleteAll(MARKER_DEBUG_LINE)
            handle = self.markerAdd(int(line), MARKER_DEBUG_LINE)
            self.ensureLineVisible(int(line))
            return handle >= 0
        except Exception as e:
            print(f"[EditorWidget] 高亮调试行失败: {e}")
            return False

    def clear_debug_line(self):
        """清除"当前执行行"高亮。"""
        try:
            self.markerDeleteAll(MARKER_DEBUG_LINE)
        except Exception:
            pass

    # ========================================================
    # 右键上下文菜单
    # ========================================================
    def contextMenuEvent(self, event: QContextMenuEvent):
        """右键上下文菜单"""
        menu = QMenu(self)

        # 撤销/重做
        proxy = self.proxy
        if proxy:
            undo_act = menu.addAction("↩ 撤销")
            undo_act.setEnabled(proxy.can_undo())
            undo_act.triggered.connect(proxy.undo)

            redo_act = menu.addAction("↪ 重做")
            redo_act.setEnabled(proxy.can_redo())
            redo_act.triggered.connect(proxy.redo)

        menu.addSeparator()

        # 剪切/复制/粘贴
        has_selection = self.hasSelectedText()

        cut_act = menu.addAction("✂ 剪切")
        cut_act.setEnabled(has_selection)
        cut_act.triggered.connect(self.cut)

        copy_act = menu.addAction("📋 复制")
        copy_act.setEnabled(has_selection)
        copy_act.triggered.connect(self.copy)

        paste_act = menu.addAction("📋 粘贴")
        paste_act.triggered.connect(self.paste)

        menu.addSeparator()

        # 选区操作
        if has_selection:
            select_next = menu.addAction("🔷 选中下一个相同项")
            select_next.triggered.connect(proxy.select_next_occurrence)

            calc_act = menu.addAction("🧮 计算表达式")
            calc_act.triggered.connect(proxy.eval_expression)

            comment_act = menu.addAction("💬 注释/取消注释")
            comment_act.triggered.connect(proxy.toggle_line_comment)

            menu.addSeparator()

            upper_act = menu.addAction("🔠 转为大写")
            upper_act.triggered.connect(proxy.to_upper)

            lower_act = menu.addAction("🔡 转为小写")
            lower_act.triggered.connect(proxy.to_lower)

            toggle_case = menu.addAction("🔤 大小写切换")
            toggle_case.triggered.connect(proxy.toggle_case)

            menu.addSeparator()

        # 列编辑器（核心功能）
        #
        # 与 Edit 菜单「列编辑器…」(Alt+Shift+I) 走**同一个** API
        # （ui/column_editor_dialog.show_column_editor）：
        # 在矩形选区（SC_SEL_RECTANGLE）/ 多光标 / 当前选区的多行上
        # 逐行插入文本或递增数字，整次编辑只产生一条撤销命令。
        col_act = menu.addAction("📊 列编辑器…")
        col_act.triggered.connect(self.open_column_editor)

        # 行操作
        line_ops = menu.addMenu("📝 行操作")
        line_ops.addAction("上移行", proxy.move_line_up)
        line_ops.addAction("下移行", proxy.move_line_down)
        line_ops.addAction("复制行", proxy.duplicate_line)
        line_ops.addAction("删除行", proxy.delete_line)

        # 书签
        line, _ = self.getCursorPosition()
        is_bookmarked = bool(self.markersAtLine(line) & (1 << MARKER_BOOKMARK))
        bookmark_text = "🔖 移除书签" if is_bookmarked else "🔖 添加书签"

        bookmark_act = menu.addAction(bookmark_text)
        bookmark_act.triggered.connect(proxy.toggle_bookmark)

        # 断点（D3）：右键菜单入口，与 F9 / 装订线单击等价
        is_breakpoint = bool(
            self.markersAtLine(line) & (1 << MARKER_BREAKPOINT)
        )
        bp_text = "🔴 移除断点 (F9)" if is_breakpoint else "🔴 添加断点 (F9)"
        bp_act = menu.addAction(bp_text)
        bp_act.triggered.connect(
            lambda _checked=False, ln=line: self._toggle_breakpoint_at_line(ln)
        )

        menu.addSeparator()

        # 查找
        find_act = menu.addAction("🔍 查找...")
        find_act.triggered.connect(self._trigger_find)

        goto_line = menu.addAction("📍 跳转到行...")
        goto_line.triggered.connect(self._trigger_goto_line)

        menu.addSeparator()

        # 插入日期时间
        datetime_act = menu.addAction("📅 插入日期时间")
        datetime_act.triggered.connect(proxy.insert_datetime)

        # 清理
        clean_menu = menu.addMenu("🧹 清理")
        clean_menu.addAction("清除行尾空白",
                              proxy.trim_trailing_whitespace)
        clean_menu.addAction("删除空行", proxy.remove_blank_lines)

        menu.addSeparator()

        # 全选
        select_all = menu.addAction("全选")
        select_all.triggered.connect(self.selectAll)

        # 显示菜单
        menu.exec_(event.globalPos())

    def _trigger_find(self):
        """触发查找面板"""
        win = self.window()
        if hasattr(win, 'show_search'):
            win.show_search()

    def _trigger_goto_line(self):
        """触发跳转到行"""
        from PyQt5.QtWidgets import QInputDialog

        total_lines = self.SendScintilla(QsciScintilla.SCI_GETLINECOUNT)
        line, ok = QInputDialog.getInt(
            self, "跳转到行", "行号:",
            1, 1, total_lines
        )
        if ok:
            self.setCursorPosition(line - 1, 0)
            self.ensureLineVisible(line - 1)

    # ========================================================
    # 拖放支持
    # ========================================================
    def dragEnterEvent(self, event: QDragEnterEvent):
        """拖入事件"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent):
        """放下事件"""
        if not event.mimeData().hasUrls():
            super().dropEvent(event)
            return

        urls = event.mimeData().urls()

        for url in urls:
            if url.isLocalFile():
                filepath = url.toLocalFile()
                if os.path.isfile(filepath):
                    self.file_dropped.emit(filepath)

        event.acceptProposedAction()

    # ========================================================
    # 焦点事件
    # ========================================================
    def focusInEvent(self, event):
        """获得焦点"""
        super().focusInEvent(event)
        self.focus_received.emit()

    # ========================================================
    # 快捷键
    # ========================================================
    def copy(self):
        """重写复制，无选区时忽略"""
        if self.hasSelectedText():
            super().copy()

    def cut(self):
        """重写剪切，无选区时忽略"""
        if self.hasSelectedText():
            super().cut()

    # ========================================================
    # 便捷方法
    # ========================================================
    def apply_preferences(self):
        """重新应用偏好设置"""
        try:
            font = self.prefs.build_font()
            self.setFont(font)
            self.setMarginsFont(font)

            self.setTabWidth(self.prefs.get("tab_width", 4))
            self.setIndentationWidth(self.prefs.get("tab_width", 4))
            self.setIndentationsUseTabs(
                self.prefs.get("indent_use_tabs", False)
            )
            self.setIndentationGuides(
                self.prefs.get("indent_guides", True)
            )

            self.setCaretLineVisible(
                self.prefs.get("show_current_line", True)
            )

            self._rainbow_enabled = self.prefs.get("indent_rainbow", False)
            self._cursor_trail_enabled = self.prefs.get("cursor_trail", False)
            self._smart_highlight_enabled = self.prefs.get(
                "smart_highlight", True
            )

            # P10: 尊重补全开关（默认开启）与触发门槛
            self._completion_enabled = bool(
                self.prefs.get("local_completion", DEFAULT_LOCAL_COMPLETION)
            )
            self._completion_min_prefix = max(
                COMPLETION_MIN_PREFIX,
                int(self.prefs.get("local_completion_min_prefix", COMPLETION_MIN_PREFIX)),
            )
            self._completion_cache.clear()

            self.viewport().update()

        except Exception as e:
            print(f"[EditorWidget] 应用偏好失败: {e}")

    def get_line_count(self) -> int:
        """获取行数"""
        return self.SendScintilla(QsciScintilla.SCI_GETLINECOUNT)

    # ========================================================
    # 列编辑器（核心功能）
    # ========================================================
    def open_column_editor(self):
        """打开列编辑器对话框。

        对标 Notepad++ 的 Edit → Column Editor…：在矩形选区
        （``SC_SEL_RECTANGLE``）/ 多光标 / 当前选区的多行上，逐行插入
        同一段文本或递增数字序列，整次编辑只产生**一条**撤销命令。

        实现集中在 ``ui/column_editor_dialog.py``（本文件只做入口，
        与 Edit 菜单、右键菜单调用同一个 ``show_column_editor``）：

        返回:
            ``ColumnEditResult``（用户取消时返回 None）
        """
        try:
            from ui.column_editor_dialog import show_column_editor
            return show_column_editor(self, self)
        except Exception as e:
            print(f"[EditorWidget] 列编辑器失败: {e}")
            return None

    def get_char_count(self) -> int:
        """获取字符数"""
        return self.SendScintilla(QsciScintilla.SCI_GETLENGTH)

    def get_line_text(self, line: int) -> str:
        """获取指定行的文本"""
        try:
            return self.text(line)
        except Exception:
            return ""

    def get_info(self) -> Dict[str, Any]:
        """获取编辑器信息"""
        line, col = self.getCursorPosition()

        return {
            'line': line + 1,
            'col': col,
            'line_count': self.get_line_count(),
            'char_count': self.get_char_count(),
            'has_selection': self.hasSelectedText(),
            'modified': self.isModified(),
            'readonly': self.isReadOnly(),
            'lexer': type(self.lexer()).__name__ if self.lexer() else "无",
            'selections': self.SendScintilla(
                QsciScintilla.SCI_GETSELECTIONS
            ),
            'folded_lines': sum(
                1 for i in range(self.get_line_count())
                if not self.SendScintilla(
                    QsciScintilla.SCI_GETFOLDEXPANDED, i
                )
            ),
        }

    def dump(self) -> str:
        """导出编辑器信息"""
        info = self.get_info()
        lines = ["EditorWidget", "=" * 60]
        for k, v in info.items():
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        info = self.get_info()
        return (f"<EditorWidget line={info['line']} "
                f"col={info['col']} "
                f"modified={info['modified']}>")


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication, QMainWindow

    app = QApplication(sys.argv)

    # 创建主窗口
    win = QMainWindow()
    win.setWindowTitle("EditorWidget 测试")
    win.resize(900, 700)

    # 创建编辑器
    editor = EditorWidget()
    win.setCentralWidget(editor)
    win.show()

    # 加载测试内容
    test_content = '''#!/usr/bin/env python
# -*- coding: utf-8 -*-

def main():
    """主函数"""
    message = "Hello, 青草编辑器!"
    print(message)
    
    if True:
        print("测试缩进")
        if True:
            print("二级缩进")
            if True:
                print("三级缩进")
    
    return 0


class MyClass:
    def __init__(self):
        self.value = 42
    
    def method(self):
        return self.value


if __name__ == "__main__":
    main()
'''

    editor.setText(test_content)
    editor.set_lexer_by_filename("test.py")

    # 启用缩进彩虹线
    editor.set_rainbow_enabled(True)

    print("=== EditorWidget 测试 ===")
    print(editor.dump())
    print()

    # 定时退出
    QTimer.singleShot(5000, app.quit)

    sys.exit(app.exec())