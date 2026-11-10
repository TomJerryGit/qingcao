# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405,F811
"""编辑器视图（v2.24 拆分：输入/绘制/补全/词法）。"""

from ui.editor_view_common import *  # noqa: F401,F403,F405
from ui.editor_view_completion import EditorCompletionMixin
from ui.editor_view_input import EditorInputMixin
from ui.editor_view_lexer import EditorLexerMixin
from ui.editor_view_paint import EditorPaintMixin


class EditorWidget(
    EditorInputMixin,
    EditorPaintMixin,
    EditorCompletionMixin,
    EditorLexerMixin,
    QsciScintilla,
):
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

    def __init__(self, provider=None, prefs: Optional[Preferences] = None, parent=None):
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

        # 大文档模式状态（性能优化，见 is_large_document）
        self._last_lexer_filepath: Optional[str] = None
        self._large_doc_mode: bool = False

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
        self.setBackspaceUnindents(self.prefs.get("indent_backspace_unindent", True))
        self.setTabIndents(True)

        # 换行
        wrap_mode = self.prefs.get("word_wrap", False)
        if wrap_mode:
            self.setWrapMode(QsciScintilla.WrapWord)
        else:
            self.setWrapMode(QsciScintilla.WrapNone)

        # 光标
        self.setCaretLineVisible(self.prefs.get("show_current_line", True))
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
            self.setSelectionBackgroundColor(QColor(self.prefs.get("selection_color", "#264F78")))
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
            self.indicatorDefine(QsciScintilla.INDIC_STRAIGHTBOX, INDICATOR_SEARCH)
            self.setIndicatorForegroundColor(QColor(255, 255, 0, 120), INDICATOR_SEARCH)
            self.setIndicatorOutlineColor(QColor(255, 200, 0), INDICATOR_SEARCH)

            # 当前匹配（橙色）
            self.indicatorDefine(QsciScintilla.INDIC_ROUNDBOX, INDICATOR_CURRENT_MATCH)
            self.setIndicatorForegroundColor(QColor(255, 128, 0, 180), INDICATOR_CURRENT_MATCH)

            # LSP 错误（红色波浪线）
            self.indicatorDefine(QsciScintilla.INDIC_SQUIGGLE, INDICATOR_LSP_ERROR)
            self.setIndicatorForegroundColor(QColor(255, 0, 0), INDICATOR_LSP_ERROR)

            # 代码片段占位符（蓝色）
            self.indicatorDefine(QsciScintilla.INDIC_STRAIGHTBOX, INDICATOR_SNIPPET)
            self.setIndicatorForegroundColor(QColor(0, 120, 215, 100), INDICATOR_SNIPPET)

            # 光标拖尾（淡黄）
            self.indicatorDefine(QsciScintilla.INDIC_STRAIGHTBOX, INDICATOR_CURSOR_TRAIL)
            self.setIndicatorForegroundColor(QColor(255, 255, 0, 80), INDICATOR_CURSOR_TRAIL)

            # 智能高亮（灰）
            self.indicatorDefine(QsciScintilla.INDIC_STRAIGHTBOX, INDICATOR_SMART_HIGHLIGHT)
            self.setIndicatorForegroundColor(QColor(100, 100, 100, 60), INDICATOR_SMART_HIGHLIGHT)

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
            self.setMarkerBackgroundColor(QColor(0, 255, 0, 40), MARKER_GIT_ADDED)

            self.markerDefine(QsciScintilla.Background, MARKER_GIT_MODIFIED)
            self.setMarkerBackgroundColor(QColor(0, 120, 215, 40), MARKER_GIT_MODIFIED)

            self.markerDefine(QsciScintilla.Background, MARKER_GIT_DELETED)
            self.setMarkerBackgroundColor(QColor(255, 0, 0, 40), MARKER_GIT_DELETED)

            # 断点（红圆）
            self.markerDefine(QsciScintilla.Circle, MARKER_BREAKPOINT)
            self.setMarkerBackgroundColor(QColor("#ff0000"), MARKER_BREAKPOINT)

            # 调试器当前停住的行（D3）：背景高亮。
            # Background 类型直接画在文本区，不依赖任何边距宽度。
            self.markerDefine(QsciScintilla.Background, MARKER_DEBUG_LINE)
            self.setMarkerBackgroundColor(QColor("#ffcc00"), MARKER_DEBUG_LINE)

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

    def apply_preferences(self):
        """重新应用偏好设置"""
        try:
            font = self.prefs.build_font()
            self.setFont(font)
            self.setMarginsFont(font)

            self.setTabWidth(self.prefs.get("tab_width", 4))
            self.setIndentationWidth(self.prefs.get("tab_width", 4))
            self.setIndentationsUseTabs(self.prefs.get("indent_use_tabs", False))
            self.setIndentationGuides(self.prefs.get("indent_guides", True))

            self.setCaretLineVisible(self.prefs.get("show_current_line", True))

            self._rainbow_enabled = self.prefs.get("indent_rainbow", False)
            self._cursor_trail_enabled = self.prefs.get("cursor_trail", False)
            self._smart_highlight_enabled = self.prefs.get("smart_highlight", True)

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
            "line": line + 1,
            "col": col,
            "line_count": self.get_line_count(),
            "char_count": self.get_char_count(),
            "has_selection": self.hasSelectedText(),
            "modified": self.isModified(),
            "readonly": self.isReadOnly(),
            "lexer": type(self.lexer()).__name__ if self.lexer() else "无",
            "selections": self.SendScintilla(QsciScintilla.SCI_GETSELECTIONS),
            "folded_lines": sum(
                1
                for i in range(self.get_line_count())
                if not self.SendScintilla(QsciScintilla.SCI_GETFOLDEXPANDED, i)
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
        return f"<EditorWidget line={info['line']} col={info['col']} modified={info['modified']}>"


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
