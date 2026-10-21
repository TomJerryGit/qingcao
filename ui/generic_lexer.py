# -*- coding: utf-8 -*-
"""通用声明式语言词法器（QsciLexerCustom + LanguagePack）

`core/language_pack.py` 的运行时解释器：把 JSON 语言包变成真正的
Scintilla 语法高亮，无需为每门语言写 Python 类。

样式编号（固定，便于测试断言）：
    0 默认  1 关键字  2 注释  3 字符串  4 数字  5 标识符

性能与正确性约束：
* Scintilla 的位置是**字节偏移**，这里按字节扫描（`SCI_GETCHARAT`）；
* 文档超过 `MAX_STYLE_BYTES`（1MB）时只上默认样式 —— 超大文件本来就被
  「大文档模式」关闭高亮，这里避免逐字节扫描拖垮 UI；
* 块注释/字符串可跨 `styleText` 区间：`start == 0` 时重置状态，
  其余情况延续上一次状态（Scintilla 整篇重排时按顺序调用）。
"""
from PyQt5.Qsci import QsciLexerCustom
from PyQt5.QtGui import QColor

from core.language_pack import LanguagePack


STYLE_DEFAULT = 0
STYLE_KEYWORD = 1
STYLE_COMMENT = 2
STYLE_STRING = 3
STYLE_NUMBER = 4
STYLE_IDENTIFIER = 5

MAX_STYLE_BYTES = 1024 * 1024

_DARK_COLORS = {
    STYLE_DEFAULT: "#d4d4d4",
    STYLE_KEYWORD: "#569cd6",
    STYLE_COMMENT: "#6a9955",
    STYLE_STRING: "#ce9178",
    STYLE_NUMBER: "#b5cea8",
    STYLE_IDENTIFIER: "#9cdcfe",
}
_DARK_PAPER = "#1e1e1e"


class GenericLexer(QsciLexerCustom):
    """根据 LanguagePack 生成的高亮器"""

    def __init__(self, pack: LanguagePack, parent=None, colors=None,
                 paper: str = ""):
        super().__init__(parent)
        self.pack = pack
        self._colors = dict(_DARK_COLORS)
        if colors is not None:
            # ThemeColors（见 infrastructure.theme_loader）
            try:
                self._colors = {
                    STYLE_DEFAULT: colors.foreground,
                    STYLE_KEYWORD: colors.keyword,
                    STYLE_COMMENT: colors.comment,
                    STYLE_STRING: colors.string,
                    STYLE_NUMBER: colors.number,
                    STYLE_IDENTIFIER: colors.identifier,
                }
                paper = paper or colors.background
            except Exception:
                pass
        self._paper = paper or _DARK_PAPER
        paper_color = QColor(self._paper)
        for style in range(6):
            self.setColor(self._color_hex(style), style)
            self.setPaper(paper_color, style)
        self._in_block = False
        self._in_string = ""
        self._text = ""
        self._kw_lower = {str(k).lower() for k in pack.keywords}
        self._kw_exact = {str(k) for k in pack.keywords}

    # --------------------------------------------------------
    def _color_hex(self, style: int):
        return QColor(self._colors.get(style, "#d4d4d4"))

    def language(self):
        return self.pack.name or "Declarative"

    def description(self, style=0):
        return "declarative-" + (self.pack.name or "language")

    # --------------------------------------------------------
    def styleText(self, start, end):
        editor = self.editor()
        if editor is None:
            return
        try:
            length = editor.length()
        except Exception:
            return
        if length > MAX_STYLE_BYTES:
            self.startStyling(start)
            self.setStyling(max(0, end - start), STYLE_DEFAULT)
            return
        if start == 0:
            self._in_block = False
            self._in_string = ""
            self._text = editor.text()
        self.startStyling(start)

        text = self._text
        raw = text.encode("utf-8", "replace")
        end = min(end, len(raw))
        pos = start
        while pos < end:
            style, width = self._classify(raw, pos)
            self.setStyling(width, style)
            pos += width

    def _classify(self, raw: bytes, pos: int):
        """返回 (样式, 字节宽度)"""
        pack = self.pack
        rest = raw[pos:pos + 8]
        # 块注释结束
        if self._in_block:
            end_tok = pack.block_comment[1].encode("utf-8")
            if end_tok and rest.startswith(end_tok):
                self._in_block = False
                return STYLE_COMMENT, len(end_tok)
            return STYLE_COMMENT, 1
        # 字符串延续
        if self._in_string:
            quote = self._in_string.encode("utf-8")
            if rest.startswith(b"\\"):
                return STYLE_STRING, min(2, len(rest))
            if rest.startswith(quote):
                self._in_string = ""
                return STYLE_STRING, len(quote)
            return STYLE_STRING, 1

        ch = raw[pos:pos + 1]
        # 块注释开始
        start_tok = pack.block_comment[0].encode("utf-8") \
            if pack.block_comment[0] else b""
        if start_tok and rest.startswith(start_tok):
            self._in_block = True
            return STYLE_COMMENT, len(start_tok)
        # 行注释
        if pack.line_comment:
            lc = pack.line_comment.encode("utf-8")
            if rest.startswith(lc):
                return STYLE_COMMENT, min(len(lc), len(rest))
        # 字符串开始
        for quote in pack.strings:
            qb = quote.encode("utf-8")
            if rest.startswith(qb):
                self._in_string = quote
                return STYLE_STRING, len(qb)
        # 数字
        if ch.isdigit():
            return STYLE_NUMBER, 1
        # 标识符/关键字：抓取完整单词后按配置判定
        if ch.isalpha() or ch == b"_" or ch[0] >= 0x80:
            n = 0
            total = len(raw)
            while pos + n < total:
                c = raw[pos + n:pos + n + 1]
                if not (c.isalnum() or c == b"_" or c[0] >= 0x80):
                    break
                n += 1
            n = max(1, n)
            word = raw[pos:pos + n].decode("utf-8", "ignore")
            if self.pack.case_sensitive:
                is_kw = word in self._kw_exact
            else:
                is_kw = word.lower() in self._kw_lower
            return (STYLE_KEYWORD if is_kw else STYLE_IDENTIFIER), n
        return STYLE_DEFAULT, 1


def create_generic_lexer(pack: LanguagePack, parent=None):
    """按当前主题创建语言包高亮器"""
    colors = None
    paper = ""
    try:
        win = parent.window() if parent is not None else None
        theme = getattr(win, "_startup_theme", None)
        if theme is not None:
            colors = theme.colors
    except Exception:
        colors = None
    return GenericLexer(pack, parent=parent, colors=colors, paper=paper)


__all__ = [
    "STYLE_COMMENT",
    "STYLE_DEFAULT",
    "STYLE_IDENTIFIER",
    "STYLE_KEYWORD",
    "STYLE_NUMBER",
    "STYLE_STRING",
    "GenericLexer",
    "create_generic_lexer",
]
