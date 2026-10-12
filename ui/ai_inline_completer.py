# -*- coding: utf-8 -*-
"""AI 行内补全"""
import time

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import QApplication


class AIInlineCompleter(QObject):
    """AI 行内补全器（Ghost Text 风格）"""

    completion_ready = pyqtSignal(str)

    def __init__(self, editor, ai_client, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.ai_client = ai_client
        self.enabled = False
        self._pending = False
        self._last_request_time = 0
        self._min_interval = 1.5  # 秒，防止频繁请求

        # 防抖定时器
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(500)
        self._debounce.timeout.connect(self._do_complete)

        self._current_suggestion = ""
        self._suggestion_shown = False

        # 连接信号
        self.completion_ready.connect(self._show_suggestion)

    def set_enabled(self, enabled):
        """启用/禁用"""
        self.enabled = enabled
        if not enabled:
            self._clear_suggestion()

    def on_text_changed(self):
        """文本变化时触发"""
        if not self.enabled or self._pending:
            return

        now = time.time()
        if now - self._last_request_time < self._min_interval:
            return

        # 清除旧建议
        self._clear_suggestion()

        # 防抖
        self._debounce.start()

    def _do_complete(self):
        """执行补全请求"""
        if not self.editor or not self.ai_client:
            return

        # 获取上下文
        line, col = self.editor.getCursorPosition()
        if col < 3:  # 至少输入 3 个字符才触发
            return

        # 取前 20 行
        start_line = max(0, line - 20)
        context_lines = []
        for i in range(start_line, line + 1):
            try:
                text = self.editor.text(i)
                if i == line:
                    text = text[:col]
                context_lines.append(text)
            except Exception:
                pass

        if not context_lines:
            return

        context = "\n".join(context_lines)

        self._pending = True
        self._last_request_time = time.time()

        # 异步请求
        import threading
        def worker():
            try:
                result = self.ai_client._chat([
                    {"role": "user", "content":
                        "基于以下代码，只输出接下来最可能的一行代码，"
                        "不要解释，不要重复已有内容：\n```\n"
                        + context + "\n```\n继续："}
                ], system="你是代码补全引擎，只输出一行补全内容。")
                if result:
                    # 清理
                    result = result.strip()
                    # 只取第一行
                    if '\n' in result:
                        result = result.split('\n')[0]
                    # 去掉 markdown 代码块
                    result = result.replace('```', '').strip()
                    if result:
                        self.completion_ready.emit(result)
            except Exception as e:
                print("[AIInline] 补全失败: %s" % e)
            finally:
                self._pending = False

        threading.Thread(target=worker, daemon=True).start()

    def _show_suggestion(self, text):
        """显示补全建议（用 tooltip 风格）"""
        if not text or not self.editor:
            return

        self._current_suggestion = text
        self._suggestion_shown = True

        # 用 QScintilla 的 call tip 显示
        try:
            self.editor.SendScintilla(
                self.editor.SCI_CALLTIPSHOW,
                self.editor.SendScintilla(self.editor.SCI_GETCURRENTPOS),
                text.encode('utf-8')
            )
        except Exception:
            pass

        # 5 秒后自动清除
        QTimer.singleShot(5000, self._clear_suggestion)

    def _clear_suggestion(self):
        """清除建议"""
        if not self.editor:
            return
        try:
            self.editor.SendScintilla(self.editor.SCI_CALLTIPCANCEL)
        except Exception:
            pass
        self._current_suggestion = ""
        self._suggestion_shown = False

    def accept_suggestion(self):
        """接受建议"""
        if not self._current_suggestion or not self.editor:
            return False

        try:
            self.editor.SendScintilla(self.editor.SCI_CALLTIPCANCEL)
            pos = self.editor.SendScintilla(self.editor.SCI_GETCURRENTPOS)
            self.editor.SendScintilla(
                self.editor.SCI_INSERTTEXT, pos,
                self._current_suggestion.encode('utf-8')
            )
            self._clear_suggestion()
            return True
        except Exception:
            return False