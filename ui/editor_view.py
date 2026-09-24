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
import sys
import time
from typing import Optional, List, Dict, Any, Tuple

from PyQt5.Qsci import QsciScintilla, QsciLexerPython, QsciLexerCPP
from PyQt5.QtCore import Qt, QTimer, QRectF, QPoint, QMimeData, QUrl, pyqtSignal
from PyQt5.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush, QKeyEvent, QMouseEvent,
    QDragEnterEvent, QDropEvent, QContextMenuEvent, QWheelEvent
)
from PyQt5.QtWidgets import QApplication, QMenu, QMessageBox

from app.preferences import Preferences
from core.document import Document
from core.editor import EditorProxy
from core.document import LocalFileProvider
from core.content_provider import MemoryProvider


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

        # 配置
        self._configure()

        # 初始化指示器
        self._init_indicators()

        # 初始化标记
        self._init_markers()

        # 连接信号
        self._connect_signals()

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

        # 自动补全
        self.setAutoCompletionSource(QsciScintilla.AcsAll)
        self.setAutoCompletionThreshold(2)
        self.setAutoCompletionCaseSensitivity(False)
        self.setAutoCompletionReplaceWord(False)

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

        except Exception as e:
            print(f"[EditorWidget] 初始化标记失败: {e}")

    def _connect_signals(self):
        """连接内部信号"""
        try:
            self.cursorPositionChanged.connect(self._on_cursor_moved)
            self.SCN_CHARADDED.connect(self._on_char_added)
        except Exception:
            pass

    # ========================================================
    # 语法高亮
    # ========================================================
    def set_lexer_by_filename(self, filepath: Optional[str]):
        """根据文件扩展名设置词法器"""
        if not filepath:
            self.setLexer(None)
            return

        ext = os.path.splitext(filepath)[1].lower()

        try:
            if ext in ('.py', '.pyw'):
                self.setLexer(QsciLexerPython())
            elif ext in ('.cpp', '.cc', '.cxx', '.h', '.hpp', '.c'):
                self.setLexer(QsciLexerCPP())
            elif ext == '.log':
                # 使用自定义日志词法器（如果存在）
                try:
                    from core.log_lexer import LogLexer
                    self.setLexer(LogLexer(self))
                except ImportError:
                    self.setLexer(None)
            else:
                # 检查自定义词法器注册表
                custom = getattr(self.window(), '_custom_lexers', {})
                if ext in custom:
                    try:
                        factory = custom[ext]
                        lexer = factory()
                        if lexer:
                            self.setLexer(lexer)
                            return
                    except Exception:
                        pass
                self.setLexer(None)
        except Exception as e:
            print(f"[EditorWidget] 设置词法器失败: {e}")
            self.setLexer(None)

    def set_lexer(self, lexer):
        """重写，同时设置字体"""
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
        """
        key = event.key()
        text = event.text()
        modifiers = event.modifiers()

        # Esc：清除多光标
        if key == Qt.Key_Escape:
            if self.SendScintilla(QsciScintilla.SCI_GETSELECTIONS) > 1:
                self.proxy.clear_multi_cursors()
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
        """字符输入后的回调"""
        try:
            char = chr(char_code)

            # 自动补全右符号（无选区时）
            if char in PAIRS and not self.hasSelectedText():
                close_char = PAIRS[char]
                if char != close_char:  # 不是成对的相同字符
                    # 自动插入右符号
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

            self.viewport().update()

        except Exception as e:
            print(f"[EditorWidget] 应用偏好失败: {e}")

    def get_line_count(self) -> int:
        """获取行数"""
        return self.SendScintilla(QsciScintilla.SCI_GETLINECOUNT)

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