#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
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

import os
import sys
import io
import time
import traceback
import contextlib
import builtins
from typing import Optional, List, Dict, Any, Tuple, Callable, Set
from enum import Enum, auto

from PyQt5.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QLineEdit, QPushButton, QToolButton, QLabel, QMenu,
    QMessageBox, QFileDialog, QSplitter, QTextEdit, QApplication,
    QCompleter, QScrollBar, QFrame, QSizePolicy
)
from PyQt5.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QTextCharFormat,
    QSyntaxHighlighter,
    QTextCursor,
    QKeySequence,
    QFontDatabase,
    QPalette,
    QTextFormat,
)
from PyQt5.QtWidgets import QAction
from PyQt5.QtCore import (
    Qt, pyqtSignal, QTimer, QSettings, QPoint, QStringListModel,
    QSize, QEvent
)

from app.event_bus import (
    bus, StatusMessageEvent, NotificationEvent
)


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
COLOR_PROMPT = QColor("#7ec850")        # 绿色提示符
COLOR_OUTPUT = QColor("#d4d4d4")        # 普通输出
COLOR_ERROR = QColor("#f14c4c")         # 错误输出
COLOR_WARNING = QColor("#f0ad4e")       # 警告输出
COLOR_INFO = QColor("#4dabf7")          # 信息输出
COLOR_SUCCESS = QColor("#7ec850")       # 成功输出
COLOR_RESULT = QColor("#ce9178")        # 表达式结果
COLOR_COMMENT = QColor("#6a9955")       # 注释
COLOR_STRING = QColor("#ce9178")        # 字符串
COLOR_KEYWORD = QColor("#569cd6")       # 关键字
COLOR_NUMBER = QColor("#b5cea8")        # 数字

# Python 关键字
PYTHON_KEYWORDS = {
    'False', 'None', 'True', 'and', 'as', 'assert', 'async',
    'await', 'break', 'class', 'continue', 'def', 'del',
    'elif', 'else', 'except', 'finally', 'for', 'from',
    'global', 'if', 'import', 'in', 'is', 'lambda',
    'nonlocal', 'not', 'or', 'pass', 'raise', 'return',
    'try', 'while', 'with', 'yield',
}

PYTHON_BUILTINS = {
    'abs', 'all', 'any', 'bin', 'bool', 'bytes', 'callable',
    'chr', 'dict', 'dir', 'divmod', 'enumerate', 'eval',
    'filter', 'float', 'format', 'frozenset', 'getattr',
    'globals', 'hasattr', 'hash', 'help', 'hex', 'id',
    'input', 'int', 'isinstance', 'issubclass', 'iter',
    'len', 'list', 'locals', 'map', 'max', 'min', 'next',
    'object', 'oct', 'open', 'ord', 'pow', 'print', 'range',
    'repr', 'reversed', 'round', 'set', 'setattr', 'slice',
    'sorted', 'str', 'sum', 'super', 'tuple', 'type', 'vars',
    'zip', '__import__',
}


# ============================================================
# 历史管理器
# ============================================================
class ConsoleHistory:
    """
    命令历史管理器。

    支持:
    - 添加历史
    - 上下导航
    - 持久化
    """

    def __init__(self, max_size: int = MAX_HISTORY_SIZE):
        self.max_size = max_size
        self._history: List[str] = []
        self._index: int = 0
        self._draft: str = ""  # 当前未提交的输入

        self._load()

    def add(self, text: str):
        """添加命令到历史"""
        text = text.strip()
        if not text:
            return

        # 去除连续重复
        if self._history and self._history[-1] == text:
            return

        self._history.append(text)
        if len(self._history) > self.max_size:
            self._history.pop(0)

        self._index = len(self._history)
        self._save()

    def previous(self) -> Optional[str]:
        """获取上一条命令"""
        if not self._history:
            return None

        if self._index == len(self._history):
            # 首次按上，保存草稿
            self._draft = ""  # 由外部设置

        if self._index > 0:
            self._index -= 1
            return self._history[self._index]

        return None

    def next(self) -> Optional[str]:
        """获取下一条命令"""
        if not self._history:
            return None

        if self._index < len(self._history) - 1:
            self._index += 1
            return self._history[self._index]
        elif self._index == len(self._history) - 1:
            self._index = len(self._history)
            return self._draft if self._draft else ""

        return None

    def set_draft(self, text: str):
        """设置当前草稿"""
        self._draft = text

    def reset_index(self):
        """重置索引"""
        self._index = len(self._history)

    def clear(self):
        """清空历史"""
        self._history.clear()
        self._index = 0
        self._save()

    def get_all(self) -> List[str]:
        """获取所有历史"""
        return list(self._history)

    # --------------------------------------------------------
    # 持久化
    # --------------------------------------------------------
    def _load(self):
        """加载历史"""
        try:
            import json
            settings = QSettings("QingCao", "Console")
            data = settings.value("history", "[]")
            if isinstance(data, str):
                self._history = json.loads(data)
            else:
                self._history = list(data)
            self._index = len(self._history)
        except Exception:
            self._history = []

    def _save(self):
        """保存历史"""
        try:
            import json
            settings = QSettings("QingCao", "Console")
            settings.setValue("history", json.dumps(self._history[-100:]))
        except Exception:
            pass


# ============================================================
# 输出显示控件
# ============================================================
class ConsoleOutput(QPlainTextEdit):
    """
    控制台输出显示控件。

    特性:
    - 只读
    - 语法高亮（简单）
    - 行数限制
    - 彩色输出
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setUndoRedoEnabled(False)
        self.setMaximumBlockCount(MAX_OUTPUT_LINES)

        # 字体
        font = QFont(DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE)
        font.setStyleHint(QFont.Monospace)
        self.setFont(font)

        # 应用样式
        self._apply_style()

        # 语法高亮
        self._highlighter = PythonHighlighter(self.document())

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                padding: 8px;
                selection-background-color: #264f78;
                font-family: {DEFAULT_FONT_FAMILY};
                font-size: {DEFAULT_FONT_SIZE}pt;
            }}
        """)

    def append_output(self, text: str, color: QColor = None):
        """
        追加输出。

        参数:
            text: 输出文本
            color: 文本颜色（可选）
        """
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        if color:
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            cursor.insertText(text, fmt)
        else:
            cursor.insertText(text)

        # 自动滚动
        self.moveCursor(QTextCursor.End)
        self.ensureCursorVisible()

    def append_prompt(self, text: str = PRIMARY_PROMPT):
        """追加提示符"""
        self.append_output(text, COLOR_PROMPT)

    def append_error(self, text: str):
        """追加错误"""
        self.append_output(text, COLOR_ERROR)

    def append_result(self, text: str):
        """追加结果"""
        self.append_output(text, COLOR_RESULT)

    def append_info(self, text: str):
        """追加信息"""
        self.append_output(text, COLOR_INFO)

    def append_success(self, text: str):
        """追加成功"""
        self.append_output(text, COLOR_SUCCESS)

    def append_warning(self, text: str):
        """追加警告"""
        self.append_output(text, COLOR_WARNING)

    def clear_output(self):
        """清空输出"""
        self.clear()

    def get_text(self) -> str:
        """获取全部文本"""
        return self.toPlainText()

    def get_last_lines(self, count: int = 100) -> str:
        """获取最后 N 行"""
        text = self.toPlainText()
        lines = text.split('\n')
        return '\n'.join(lines[-count:])


# ============================================================
# 语法高亮器
# ============================================================
class PythonHighlighter(QSyntaxHighlighter):
    """
    Python 语法高亮器（简化版）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._rules = []

        # 关键字（P2-4: 关键字/内置函数合并为单条正则）
        # 原实现每条关键字都生成一条正则，约 80 条规则，
        # 每行文本跑 80 次 finditer。合并后 2 条即可。
        # 按长度降序排列，长词优先尝试（避免 int 抢 isinstance）。
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(COLOR_KEYWORD)
        keyword_format.setFontWeight(QFont.Bold)
        _kw_alt = '|'.join(
            sorted(PYTHON_KEYWORDS, key=len, reverse=True)
        )
        self._rules.append((r'\b(?:' + _kw_alt + r')\b',
                            keyword_format))

        # 内置函数（同样合并）
        builtin_format = QTextCharFormat()
        builtin_format.setForeground(QColor("#dcdcaa"))
        _bi_alt = '|'.join(
            sorted(PYTHON_BUILTINS, key=len, reverse=True)
        )
        self._rules.append((r'\b(?:' + _bi_alt + r')\b',
                            builtin_format))

        # 字符串（单引号）
        string_format = QTextCharFormat()
        string_format.setForeground(COLOR_STRING)
        self._rules.append((r"'[^']*'", string_format))
        self._rules.append((r'"[^"]*"', string_format))

        # 数字
        number_format = QTextCharFormat()
        number_format.setForeground(COLOR_NUMBER)
        self._rules.append((r"\b\d+\.?\d*\b", number_format))

        # 注释
        comment_format = QTextCharFormat()
        comment_format.setForeground(COLOR_COMMENT)
        comment_format.setFontItalic(True)
        self._rules.append((r"#[^\n]*", comment_format))

        # 编译正则
        import re
        self._compiled_rules = [
            (re.compile(pattern), fmt)
            for pattern, fmt in self._rules
        ]

    def highlightBlock(self, text: str):
        """高亮文本块"""
        for pattern, fmt in self._compiled_rules:
            for match in pattern.finditer(text):
                start = match.start()
                length = match.end() - match.start()
                self.setFormat(start, length, fmt)


# ============================================================
# 输入行控件
# ============================================================
class ConsoleInput(QLineEdit):
    """
    控制台输入行。

    特性:
    - 命令历史（上下键）
    - 补全（Tab）
    - 提交信号
    """

    submitted = pyqtSignal(str)
    history_prev = pyqtSignal()
    history_next = pyqtSignal()
    tab_pressed = pyqtSignal()
    escape_pressed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # 字体
        font = QFont(INPUT_FONT_FAMILY, INPUT_FONT_SIZE)
        font.setStyleHint(QFont.Monospace)
        self.setFont(font)

        # 样式
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: #2d2d2d;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 3px;
                padding: 6px 10px;
                font-family: {INPUT_FONT_FAMILY};
                font-size: {INPUT_FONT_SIZE}pt;
                selection-background-color: #264f78;
            }}
            QLineEdit:focus {{
                border-color: #007acc;
            }}
        """)

        # 提示符
        self.setPlaceholderText("输入 Python 代码，按 Enter 执行，Shift+Enter 换行")

        # 补全器
        self._completer: Optional[QCompleter] = None

    def keyPressEvent(self, event: QKeyEvent):
        """键盘事件"""
        key = event.key()

        # 上下键：历史导航
        if key == Qt.Key_Up:
            self.history_prev.emit()
            event.accept()
            return

        if key == Qt.Key_Down:
            self.history_next.emit()
            event.accept()
            return

        # Tab：补全
        if key == Qt.Key_Tab:
            self.tab_pressed.emit()
            event.accept()
            return

        # Esc：清空或关闭
        if key == Qt.Key_Escape:
            self.escape_pressed.emit()
            event.accept()
            return

        # Enter：提交（Shift+Enter 换行）
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                # Shift+Enter：插入换行（在单行模式下忽略）
                super().keyPressEvent(event)
                return

            text = self.text()
            if text.strip():
                self.submitted.emit(text)
            event.accept()
            return

        super().keyPressEvent(event)

    def set_completer(self, completer: QCompleter):
        """设置补全器"""
        self._completer = completer
        super().setCompleter(completer)

    def complete(self):
        """触发补全"""
        if self._completer:
            self._completer.setCompletionPrefix(self.text())
            if self._completer.completionCount() > 0:
                self._completer.complete()


# ============================================================
# 代码补全器
# ============================================================
class ConsoleCompleter(QCompleter):
    """
    控制台代码补全器。

    基于:
    - Python 关键字和内置函数
    - 当前命名空间变量
    - 用户历史
    """

    def __init__(self, namespace: Dict[str, Any], parent=None):
        super().__init__(parent)

        self.namespace = namespace
        self._model = QStringListModel()
        self.setModel(self._model)
        self.setCaseSensitivity(Qt.CaseInsensitive)
        self.setCompletionMode(QCompleter.PopupCompletion)

    def update_words(self, extra_words: Optional[List[str]] = None):
        """更新补全词列表"""
        words = set()

        # 关键字
        words.update(PYTHON_KEYWORDS)

        # 内置函数
        words.update(PYTHON_BUILTINS)

        # 命名空间变量
        words.update(self.namespace.keys())

        # 额外词
        if extra_words:
            words.update(extra_words)

        # 排序
        sorted_words = sorted(words)
        self._model.setStringList(sorted_words)


# ============================================================
# Python 控制台
# ============================================================
class PythonConsole(QDockWidget):
    """
    Python 控制台。

    提供交互式 Python 解释器，可访问编辑器 API。

    信号:
        code_executed(str): 代码被执行
        console_cleared(): 控制台被清空
    """

    code_executed = pyqtSignal(str)
    console_cleared = pyqtSignal()

    def __init__(self, main_window=None, parent=None):
        """
        参数:
            main_window: 主窗口实例
            parent: 父控件
        """
        super().__init__("Python 控制台", parent or main_window)

        self.main_window = main_window
        self.setObjectName("PythonConsole")
        self.setAllowedAreas(
            Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea
        )

        # 命名空间
        self.namespace: Dict[str, Any] = {}
        self._init_namespace()

        # 历史
        self.history = ConsoleHistory()

        # 状态
        self._multi_line_buffer: List[str] = []
        self._executing: bool = False

        # 应用设置
        self._settings = QSettings("QingCao", "Console")

        # 构建 UI
        self._build_ui()

        # 连接信号
        self._connect_signals()

        # 欢迎信息
        QTimer.singleShot(100, self._show_welcome)

    # ========================================================
    # 命名空间初始化
    # ========================================================
    def _init_namespace(self):
        """初始化命名空间"""
        # 基础命名空间
        self.namespace = {
            '__name__': '__console__',
            '__doc__': None,
            '__builtins__': builtins,
        }

        # 注入编辑器 API
        self._inject_api()

    def _inject_api(self):
        """注入编辑器 API"""
        try:
            # 主窗口引用
            self.namespace['app'] = self.main_window
            self.namespace['window'] = self.main_window

            # 编辑器代理
            if self.main_window and hasattr(self.main_window, 'tabs'):
                proxy = self.main_window.tabs.current_proxy()
                self.namespace['editor'] = proxy
                self.namespace['proxy'] = proxy

                if proxy:
                    self.namespace['document'] = proxy.document
                    self.namespace['doc'] = proxy.document
                    self.namespace['sc'] = proxy.sc
                    self.namespace['scintilla'] = proxy.sc

            # 插件 API
            if self.main_window and hasattr(self.main_window, 'api'):
                self.namespace['api'] = self.main_window.api

            # 事件总线
            self.namespace['bus'] = bus

            # 动作管理器
            if self.main_window and hasattr(self.main_window, 'act_mgr'):
                self.namespace['actions'] = self.main_window.act_mgr

            # 常用模块
            import sys as _sys
            import os as _os
            import json as _json
            import re as _re
            import time as _time
            import datetime as _datetime

            self.namespace['sys'] = _sys
            self.namespace['os'] = _os
            self.namespace['json'] = _json
            self.namespace['re'] = _re
            self.namespace['time'] = _time
            self.namespace['datetime'] = _datetime

            # 便捷函数
            self.namespace['clear'] = self.clear_output
            self.namespace['help_console'] = self._show_help

        except Exception as e:
            print(f"[PythonConsole] 注入 API 失败: {e}")

    def update_editor_context(self):
        """更新编辑器上下文（切换标签时调用）"""
        try:
            if self.main_window and hasattr(self.main_window, 'tabs'):
                proxy = self.main_window.tabs.current_proxy()
                self.namespace['editor'] = proxy
                self.namespace['proxy'] = proxy

                if proxy:
                    self.namespace['document'] = proxy.document
                    self.namespace['doc'] = proxy.document
                    self.namespace['sc'] = proxy.sc
                    self.namespace['scintilla'] = proxy.sc

            # 更新补全词
            if hasattr(self, 'completer'):
                self.completer.update_words()

        except Exception as e:
            print(f"[PythonConsole] 更新上下文失败: {e}")

    # ========================================================
    # UI 构建
    # ========================================================
    def _build_ui(self):
        """构建 UI"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部工具栏
        toolbar = self._build_toolbar()
        layout.addWidget(toolbar)

        # 输出区域
        self.output = ConsoleOutput()
        layout.addWidget(self.output, 1)

        # 底部输入区域
        input_container = QWidget()
        input_container.setStyleSheet(
            "background-color: #252526; "
            "border-top: 1px solid #3c3c3c;"
        )
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(8, 6, 8, 6)
        input_layout.setSpacing(8)

        # 提示符
        self.prompt_label = QLabel(PRIMARY_PROMPT)
        self.prompt_label.setStyleSheet(
            "color: #7ec850; font-weight: bold; "
            f"font-family: {INPUT_FONT_FAMILY}; "
            f"font-size: {INPUT_FONT_SIZE}pt;"
        )
        self.prompt_label.setFixedWidth(30)
        input_layout.addWidget(self.prompt_label)

        # 输入行
        self.input_edit = ConsoleInput()
        input_layout.addWidget(self.input_edit, 1)

        # 执行按钮
        self.run_btn = QPushButton("执行")
        self.run_btn.setFixedWidth(60)
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 5px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0a4d7a;
            }
        """)
        self.run_btn.clicked.connect(self._on_run_clicked)
        input_layout.addWidget(self.run_btn)

        layout.addWidget(input_container)

        self.setWidget(container)

        # 应用样式
        self._apply_style()

        # 补全器
        self.completer = ConsoleCompleter(self.namespace, self)
        self.completer.update_words()
        self.input_edit.set_completer(self.completer)

    def _build_toolbar(self) -> QWidget:
        """构建顶部工具栏"""
        toolbar = QWidget()
        toolbar.setStyleSheet(
            "background-color: #2d2d2d; "
            "border-bottom: 1px solid #3c3c3c;"
        )
        toolbar.setFixedHeight(32)

        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(4)

        # 标题
        title = QLabel("🐍 Python 控制台")
        title.setStyleSheet(
            "color: #7ec850; font-size: 12px; "
            "font-weight: bold; padding: 0 4px;"
        )
        layout.addWidget(title)

        layout.addStretch()

        # 清空按钮
        clear_btn = QToolButton()
        clear_btn.setText("🗑")
        clear_btn.setToolTip("清空输出 (Ctrl+L)")
        clear_btn.setFixedSize(24, 24)
        clear_btn.clicked.connect(self.clear_output)
        layout.addWidget(clear_btn)

        # 执行选中代码按钮
        run_selection_btn = QToolButton()
        run_selection_btn.setText("▶")
        run_selection_btn.setToolTip("执行编辑器选中的代码")
        run_selection_btn.setFixedSize(24, 24)
        run_selection_btn.clicked.connect(self.execute_selection)
        layout.addWidget(run_selection_btn)

        # 执行当前文件按钮
        run_file_btn = QToolButton()
        run_file_btn.setText("📄")
        run_file_btn.setToolTip("执行当前编辑器的完整代码")
        run_file_btn.setFixedSize(24, 24)
        run_file_btn.clicked.connect(self.execute_current_file)
        layout.addWidget(run_file_btn)

        # 分隔
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("background-color: #3c3c3c;")
        layout.addWidget(sep)

        # 帮助按钮
        help_btn = QToolButton()
        help_btn.setText("?")
        help_btn.setToolTip("显示帮助")
        help_btn.setFixedSize(24, 24)
        help_btn.clicked.connect(self._show_help)
        layout.addWidget(help_btn)

        # 变量查看按钮
        vars_btn = QToolButton()
        vars_btn.setText("📋")
        vars_btn.setToolTip("查看变量")
        vars_btn.setFixedSize(24, 24)
        vars_btn.clicked.connect(self.show_variables)
        layout.addWidget(vars_btn)

        # 导出按钮
        export_btn = QToolButton()
        export_btn.setText("📤")
        export_btn.setToolTip("导出输出")
        export_btn.setFixedSize(24, 24)
        export_btn.clicked.connect(self.export_output)
        layout.addWidget(export_btn)

        # 关闭按钮
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setToolTip("关闭控制台")
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self.hide)
        layout.addWidget(close_btn)

        return toolbar

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QDockWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QDockWidget::title {
                background-color: #2d2d2d;
                padding: 4px 8px;
                border-bottom: 1px solid #3c3c3c;
                font-size: 12px;
            }
            QToolButton {
                background-color: transparent;
                color: #d4d4d4;
                border: none;
                border-radius: 3px;
                font-size: 14px;
                font-weight: bold;
            }
            QToolButton:hover {
                background-color: #3c3c3c;
            }
            QToolButton:pressed {
                background-color: #094771;
            }
        """)

    # ========================================================
    # 信号连接
    # ========================================================
    def _connect_signals(self):
        """连接信号"""
        self.input_edit.submitted.connect(self._on_submit)
        self.input_edit.history_prev.connect(self._on_history_prev)
        self.input_edit.history_next.connect(self._on_history_next)
        self.input_edit.tab_pressed.connect(self._on_tab_pressed)
        self.input_edit.escape_pressed.connect(self._on_escape)

    # ========================================================
    # 欢迎与帮助
    # ========================================================
    def _show_welcome(self):
        """显示欢迎信息"""
        self.output.clear()

        self.output.append_success(
            "青草编辑器 Python 控制台 v2.0\n"
        )
        self.output.append_info(
            "Python " + sys.version.split()[0] + "\n"
        )
        self.output.append_info(
            "=" * 50 + "\n"
        )
        self.output.append_output(
            "可用变量:\n"
            "  app/window  - 主窗口\n"
            "  editor/proxy - 编辑器代理\n"
            "  document/doc - 当前文档\n"
            "  sc/scintilla - QScintilla 控件\n"
            "  api         - 插件 API\n"
            "  bus         - 事件总线\n"
            "  actions     - 动作管理器\n"
            "\n"
            "可用函数:\n"
            "  clear()     - 清空输出\n"
            "  help_console() - 显示帮助\n"
            "\n"
        )
        self.output.append_info(
            "输入 Python 代码，按 Enter 执行。\n"
            "上/下键浏览历史，Tab 补全，Ctrl+L 清空。\n"
        )
        self.output.append_output("\n")

    def _show_help(self):
        """显示帮助"""
        help_text = """
============================================================
青草编辑器 Python 控制台 - 帮助
============================================================

【基础操作】
  Enter       执行当前输入
  Shift+Enter 忽略（单行输入）
  Up/Down     浏览历史命令
  Tab         代码补全
  Esc         清空输入
  Ctrl+L      清空输出

【可用变量】
  app, window     主窗口实例
  editor, proxy   当前编辑器代理
  document, doc   当前文档对象
  sc, scintilla   QScintilla 控件
  api             插件 API 对象
  bus             事件总线
  actions         动作管理器
  sys, os, json, re, time, datetime  常用模块

【常用操作示例】

1. 读取当前编辑器内容:
   >>> text = editor.get_text()
   >>> print(text[:100])

2. 插入文本:
   >>> editor.insert_text("Hello World")

3. 打开文件:
   >>> editor.open_file("/path/to/file.py")

4. 执行命令:
   >>> actions.get("file.save").trigger()

5. 触发事件:
   >>> bus.emit_status("来自控制台的消息")

6. 查看变量:
   >>> print([k for k in namespace.keys() if not k.startswith('_')])

7. 保存所有文件:
   >>> app.tabs.save_all()

【注意】
  - 执行危险代码（如 os.system）可能导致不可预知的后果
  - 控制台与编辑器共享 Python 进程，崩溃可能影响编辑器
============================================================
"""
        self.output.append_info(help_text)

    # ========================================================
    # 输入处理
    # ========================================================
    def _on_submit(self, text: str):
        """提交输入"""
        if not text.strip():
            return

        # 多行续行处理
        if self._is_incomplete(text):
            self._multi_line_buffer.append(text)
            self.prompt_label.setText(SECONDARY_PROMPT)
            self.input_edit.clear()
            return

        # 如果有缓冲，拼接
        if self._multi_line_buffer:
            self._multi_line_buffer.append(text)
            code = "\n".join(self._multi_line_buffer)
            self._multi_line_buffer.clear()
            self.prompt_label.setText(PRIMARY_PROMPT)
        else:
            code = text

        # 清空输入
        self.input_edit.clear()

        # 显示输入
        self.output.append_prompt()
        self.output.append_output(code + "\n")

        # 执行代码
        self._execute(code)

        # 记录历史
        self.history.add(code)
        self.history.reset_index()

    def _is_incomplete(self, text: str) -> bool:
        """
        判断代码是否需要续行。

        简化实现：检查是否以 : 结尾，或括号不匹配。
        """
        stripped = text.rstrip()

        # 以冒号结尾（如 if/for/def）
        if stripped.endswith(':'):
            return True

        # 以反斜杠结尾（显式续行）
        if stripped.endswith('\\'):
            return True

        # 括号不匹配
        try:
            import ast
            ast.parse(text)
            return False
        except SyntaxError as e:
            # 检查是否为意外 EOF
            if 'unexpected EOF' in str(e).lower():
                return True
            if 'was never closed' in str(e).lower():
                return True
            return False
        except Exception:
            return False

    def _on_run_clicked(self):
        """执行按钮点击"""
        text = self.input_edit.text()
        if text.strip():
            self._on_submit(text)

    def _on_history_prev(self):
        """上一条历史"""
        current = self.input_edit.text()
        self.history.set_draft(current)

        prev = self.history.previous()
        if prev is not None:
            self.input_edit.setText(prev)

    def _on_history_next(self):
        """下一条历史"""
        nxt = self.history.next()
        if nxt is not None:
            self.input_edit.setText(nxt)

    def _on_tab_pressed(self):
        """Tab 补全"""
        self.input_edit.complete()

    def _on_escape(self):
        """Esc 键"""
        # 清空输入
        self.input_edit.clear()
        # 清空多行缓冲
        self._multi_line_buffer.clear()
        self.prompt_label.setText(PRIMARY_PROMPT)

    # ========================================================
    # 代码执行
    # ========================================================
    def _execute(self, code: str):
        """
        执行 Python 代码。

        参数:
            code: 要执行的代码
        """
        if self._executing:
            self.output.append_warning("上一次执行尚未完成\n")
            return

        self._executing = True

        # 更新上下文
        self._inject_api()

        # 捕获输出
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        try:
            # 尝试作为表达式求值（打印结果）
            result = None
            is_expression = False

            try:
                # 编译为 eval 模式
                compiled = compile(code, '<console>', 'eval')
                is_expression = True
            except SyntaxError:
                # 回退到 exec 模式
                compiled = compile(code, '<console>', 'exec')

            with contextlib.redirect_stdout(stdout_capture), \
                 contextlib.redirect_stderr(stderr_capture):

                if is_expression:
                    result = eval(compiled, self.namespace)
                else:
                    exec(compiled, self.namespace)

        except SystemExit:
            self.output.append_info("检测到 sys.exit()，已忽略\n")
        except KeyboardInterrupt:
            self.output.append_warning("执行被用户中断\n")
        except SyntaxError as e:
            self._print_syntax_error(e)
        except Exception:
            self._print_traceback()
        finally:
            self._executing = False

        # 输出 stdout
        stdout_text = stdout_capture.getvalue()
        if stdout_text:
            self.output.append_output(stdout_text)

        # 输出 stderr
        stderr_text = stderr_capture.getvalue()
        if stderr_text:
            self.output.append_error(stderr_text)

        # 输出表达式结果
        if is_expression and result is not None:
            self.output.append_result(repr(result) + "\n")

        # 更新补全词
        try:
            self.completer.update_words()
        except Exception:
            pass

        # 发射信号
        self.code_executed.emit(code)

    def _print_syntax_error(self, e: SyntaxError):
        """打印语法错误"""
        self.output.append_error(f"SyntaxError: {e.msg}\n")
        if e.lineno:
            self.output.append_error(f"  Line {e.lineno}\n")
        if e.text:
            self.output.append_error(f"  {e.text.rstrip()}\n")
            if e.offset:
                self.output.append_error(
                    "  " + " " * (e.offset - 1) + "^\n"
                )

    def _print_traceback(self):
        """打印异常堆栈"""
        exc_type, exc_value, exc_tb = sys.exc_info()

        # 过滤掉内部调用
        tb_lines = traceback.format_exception(
            exc_type, exc_value, exc_tb
        )

        # 显示最后几行
        self.output.append_error("".join(tb_lines))

    # ========================================================
    # 执行编辑器代码
    # ========================================================
    def execute_selection(self):
        """执行编辑器中选中的代码"""
        if not self.main_window:
            return

        try:
            proxy = self.main_window.tabs.current_proxy()
            if not proxy:
                self.output.append_warning("没有活动的编辑器\n")
                return

            selected = proxy.get_selected_text()
            if not selected:
                self.output.append_warning("没有选中的代码\n")
                return

            # 显示
            self.output.append_prompt()
            self.output.append_info("【执行选中代码】\n")
            self.output.append_output(selected + "\n")
            self.output.append_output("-" * 40 + "\n")

            # 执行
            self._execute(selected)

            self.output.append_output("\n")

        except Exception as e:
            self.output.append_error(f"执行失败: {e}\n")

    def execute_current_file(self):
        """执行当前编辑器的完整代码"""
        if not self.main_window:
            return

        try:
            proxy = self.main_window.tabs.current_proxy()
            if not proxy:
                self.output.append_warning("没有活动的编辑器\n")
                return

            code = proxy.get_text()
            if not code.strip():
                self.output.append_warning("当前文件为空\n")
                return

            filepath = proxy.document.filepath if proxy.document else "未命名"

            # 提示
            self.output.append_info(
                f"【执行文件: {os.path.basename(filepath)}】\n"
            )
            self.output.append_output("-" * 40 + "\n")

            # 在独立命名空间中执行（模拟 __main__）
            exec_namespace = {
                '__name__': '__main__',
                '__file__': filepath,
                '__builtins__': builtins,
            }

            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()

            try:
                with contextlib.redirect_stdout(stdout_capture), \
                     contextlib.redirect_stderr(stderr_capture):
                    exec(compile(code, filepath, 'exec'), exec_namespace)

            except SystemExit as e:
                self.output.append_info(f"程序退出 (code={e.code})\n")
            except Exception:
                self._print_traceback()

            # 输出
            stdout_text = stdout_capture.getvalue()
            if stdout_text:
                self.output.append_output(stdout_text)

            stderr_text = stderr_capture.getvalue()
            if stderr_text:
                self.output.append_error(stderr_text)

            self.output.append_info(
                "\n【执行完成】\n"
            )

        except Exception as e:
            self.output.append_error(f"执行失败: {e}\n")

    # ========================================================
    # 清空与导出
    # ========================================================
    def clear_output(self):
        """清空输出"""
        self.output.clear_output()
        self.console_cleared.emit()
        self._show_welcome()

    def export_output(self):
        """导出输出"""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出控制台输出",
            "console_output.txt",
            "文本文件 (*.txt);;所有文件 (*.*)"
        )

        if not filepath:
            return

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self.output.get_text())

            self.output.append_success(
                f"\n✓ 已导出到: {filepath}\n"
            )
        except Exception as e:
            self.output.append_error(f"\n导出失败: {e}\n")

    # ========================================================
    # 变量查看
    # ========================================================
    def show_variables(self):
        """显示当前变量"""
        try:
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView

            dlg = QDialog(self)
            dlg.setWindowTitle("控制台变量")
            dlg.resize(600, 500)

            layout = QVBoxLayout(dlg)

            table = QTableWidget()
            table.setColumnCount(3)
            table.setHeaderLabels(["名称", "类型", "值"])

            # 过滤变量
            variables = []
            for name, value in self.namespace.items():
                if name.startswith('__'):
                    continue
                if name in ('sys', 'os', 'json', 're', 'time', 'datetime'):
                    continue

                type_name = type(value).__name__
                try:
                    value_str = repr(value)[:100]
                except Exception:
                    value_str = "<无法显示>"

                variables.append((name, type_name, value_str))

            variables.sort(key=lambda x: x[0])

            table.setRowCount(len(variables))
            for i, (name, type_name, value_str) in enumerate(variables):
                table.setItem(i, 0, QTableWidgetItem(name))
                table.setItem(i, 1, QTableWidgetItem(type_name))
                table.setItem(i, 2, QTableWidgetItem(value_str))

            # 列宽
            header = table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.Stretch)

            # 样式
            table.setStyleSheet("""
                QTableWidget {
                    background-color: #1e1e1e;
                    color: #d4d4d4;
                    border: none;
                    gridline-color: #3c3c3c;
                }
                QTableWidget::item {
                    padding: 4px;
                }
                QTableWidget::item:selected {
                    background-color: #094771;
                }
                QHeaderView::section {
                    background-color: #2d2d2d;
                    color: #ccc;
                    border: none;
                    padding: 6px;
                    font-weight: bold;
                }
            """)

            layout.addWidget(table)

            # 关闭按钮
            close_btn = QPushButton("关闭")
            close_btn.clicked.connect(dlg.accept)

            from PyQt5.QtWidgets import QHBoxLayout
            btn_layout = QHBoxLayout()
            btn_layout.addStretch()
            btn_layout.addWidget(close_btn)
            layout.addLayout(btn_layout)

            dlg.exec()

        except Exception as e:
            self.output.append_error(f"显示变量失败: {e}\n")

    # ========================================================
    # 快捷键
    # ========================================================
    def keyPressEvent(self, event: QKeyEvent):
        """键盘事件"""
        # Ctrl+L：清空
        if event.key() == Qt.Key_L and \
                event.modifiers() & Qt.ControlModifier:
            self.clear_output()
            event.accept()
            return

        super().keyPressEvent(event)

    # ========================================================
    # 显示与关闭
    # ========================================================
    def showEvent(self, event):
        """显示事件"""
        super().showEvent(event)

        # 聚焦输入框
        QTimer.singleShot(50, self.input_edit.setFocus)

        # 更新上下文
        self.update_editor_context()

    # ========================================================
    # 调试
    # ========================================================
    # D: PythonConsole 主题刷新
    def refresh_theme(self, theme):
        """主题变更时刷新样式"""
        try:
            from infrastructure.theme_loader import adapt_qss_colors

            if not hasattr(self, '_original_qss'):
                self._original_qss = self.styleSheet()
                self._original_output_qss = (
                    self.output.styleSheet() if self.output else ""
                )
                self._original_input_qss = (
                    self.input_edit.styleSheet() if self.input_edit else ""
                )

            if self._original_qss:
                self.setStyleSheet(
                    adapt_qss_colors(self._original_qss, theme)
                )
            if self.output and self._original_output_qss:
                self.output.setStyleSheet(
                    adapt_qss_colors(self._original_output_qss, theme)
                )
            if self.input_edit and self._original_input_qss:
                self.input_edit.setStyleSheet(
                    adapt_qss_colors(self._original_input_qss, theme)
                )
        except Exception as e:
            print(f"[PythonConsole] refresh_theme 失败: {e}")

    def dump(self) -> str:
        """导出控制台信息"""
        lines = ["PythonConsole", "=" * 60]
        lines.append(f"Python: {sys.version.split()[0]}")
        lines.append(
            f"命名空间变量: "
            f"{len([k for k in self.namespace.keys() if not k.startswith('_')])}"
        )
        lines.append(f"历史记录: {len(self.history.get_all())}")
        lines.append(f"输出行数: {len(self.output.toPlainText().splitlines())}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<PythonConsole variables={len(self.namespace)} "
                f"history={len(self.history.get_all())}>")


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication, QMainWindow

    app = QApplication(sys.argv)

    # 创建主窗口
    win = QMainWindow()
    win.setWindowTitle("PythonConsole 测试")
    win.resize(1000, 700)
    win.show()

    # 创建控制台
    console = PythonConsole(win)
    win.addDockWidget(Qt.BottomDockWidgetArea, console)
    console.show()

    # 连接信号
    console.code_executed.connect(
        lambda code: print(f"[信号] 执行代码: {code[:50]}")
    )
    console.console_cleared.connect(
        lambda: print("[信号] 控制台清空")
    )

    # 定时测试
    def test_console():
        print("=== PythonConsole 测试 ===")
        print(console.dump())
        print()

        # 测试变量数量
        print(f"命名空间变量数: {len(console.namespace)}")

        # 测试历史
        console.history.add("print('hello')")
        console.history.add("x = 42")
        console.history.add("x * 2")

        print(f"历史记录: {console.history.get_all()}")

    QTimer.singleShot(2000, test_console)

    # 5 秒后退出
    def cleanup_and_quit():
        print()
        print(console.dump())
        app.quit()

    QTimer.singleShot(5000, cleanup_and_quit)

    sys.exit(app.exec())