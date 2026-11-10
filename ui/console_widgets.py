# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""控制台内部控件（v2.24 拆出）。"""

from ui.python_console_common import *


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
        lines = text.split("\n")
        return "\n".join(lines[-count:])


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
        _kw_alt = "|".join(sorted(PYTHON_KEYWORDS, key=len, reverse=True))
        self._rules.append((r"\b(?:" + _kw_alt + r")\b", keyword_format))

        # 内置函数（同样合并）
        builtin_format = QTextCharFormat()
        builtin_format.setForeground(QColor("#dcdcaa"))
        _bi_alt = "|".join(sorted(PYTHON_BUILTINS, key=len, reverse=True))
        self._rules.append((r"\b(?:" + _bi_alt + r")\b", builtin_format))

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

        self._compiled_rules = [(re.compile(pattern), fmt) for pattern, fmt in self._rules]

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
