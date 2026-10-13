# -*- coding: utf-8 -*-
"""AI 行内补全测试

`ui/ai_inline_completer.py` 此前是**死代码**（从未被实例化），且自带
三个缺陷；本文件锁死修复后的行为：

  1. `_pending` 不再跨线程写（改为主线程信号回调复位）
  2. 自动清除建议复用一个可重置的 `QTimer`，不再堆积不可取消的定时器
  3. 不再"输入即请求"——必须显式触发，且默认关闭

运行::

    python -m pytest tests/test_ai_inline_completer.py -v
"""
import os
import sys
import time

import pytest


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeClient:
    """可编排的假 AI 客户端"""

    def __init__(self, reply="return x + 1", delay=0.0, fail=False):
        self.reply = reply
        self.delay = delay
        self.fail = fail
        self.calls = []

    def chat_stream(self, prompt="", system="", callback=None,
                    use_history=False, max_tokens=None):
        self.calls.append({"prompt": prompt, "system": system,
                           "max_tokens": max_tokens})
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("模拟失败")
        if callback:
            callback(self.reply)
        return self.reply


def _editor(text="def f(x):\n    y = x * 2\n    "):
    from PyQt5.Qsci import QsciScintilla
    sc = QsciScintilla()
    sc.setUtf8(True)
    sc.setText(text)
    return sc


def _wait(qapp, pred, timeout=5.0):
    """驱动事件循环直到 pred() 为真"""
    end = time.time() + timeout
    while time.time() < end:
        qapp.processEvents()
        if pred():
            return True
        time.sleep(0.01)
    return False


# =========================================================
# 开关与触发门槛
# =========================================================

class TestEnableAndGating:
    def test_disabled_by_default(self, qapp):
        from ui.ai_inline_completer import AIInlineCompleter
        c = AIInlineCompleter(_editor(), FakeClient())
        assert c.enabled is False

    def test_request_returns_false_when_disabled(self, qapp):
        from ui.ai_inline_completer import AIInlineCompleter
        client = FakeClient()
        c = AIInlineCompleter(_editor(), client)
        assert c.request_now() is False
        assert client.calls == [], "未启用时不应发起请求"

    def test_set_enabled_clears_suggestion(self, qapp):
        from ui.ai_inline_completer import AIInlineCompleter
        c = AIInlineCompleter(_editor(), FakeClient())
        c.set_enabled(True)
        c._suggestion = "旧建议"
        c.set_enabled(False)
        assert c.has_suggestion() is False

    def test_no_request_when_no_client(self, qapp):
        from ui.ai_inline_completer import AIInlineCompleter
        c = AIInlineCompleter(_editor(), None)
        c.set_enabled(True)
        assert c.request_now() is False

    def test_requires_min_prefix_chars(self, qapp):
        """光标列数太少时不该浪费一次请求"""
        from ui.ai_inline_completer import AIInlineCompleter
        client = FakeClient()
        sc = _editor()
        c = AIInlineCompleter(sc, client)
        c.set_enabled(True)
        sc.setCursorPosition(2, 1)          # 只有 1 列
        assert c.request_now(force=True) is False
        assert client.calls == []

    def test_min_interval_throttles(self, qapp):
        """连按快捷键不应打爆额度（force=False 时受最小间隔限制）"""
        from ui.ai_inline_completer import AIInlineCompleter
        client = FakeClient()
        sc = _editor()
        c = AIInlineCompleter(sc, client)
        c.set_enabled(True)
        sc.setCursorPosition(2, 4)
        assert c.request_now(force=True) is True
        _wait(qapp, lambda: not c._busy)
        sc.setCursorPosition(2, 5)
        assert c.request_now() is False, "应立即被最小间隔拦下"
        assert len(client.calls) == 1

    def test_force_bypasses_interval(self, qapp):
        from ui.ai_inline_completer import AIInlineCompleter
        client = FakeClient()
        sc = _editor()
        c = AIInlineCompleter(sc, client)
        c.set_enabled(True)
        sc.setCursorPosition(2, 4)
        c.request_now(force=True)
        _wait(qapp, lambda: not c._busy)
        assert c.request_now(force=True) is True


# =========================================================
# 结果与显示
# =========================================================

class TestSuggestion:
    def test_suggestion_received(self, qapp):
        from ui.ai_inline_completer import AIInlineCompleter
        sc = _editor()
        c = AIInlineCompleter(sc, FakeClient("return x + 1"))
        c.set_enabled(True)
        sc.setCursorPosition(2, 4)
        c.request_now(force=True)
        assert _wait(qapp, lambda: c.has_suggestion())
        assert c.get_suggestion() == "return x + 1"

    def test_context_includes_previous_lines(self, qapp):
        from ui.ai_inline_completer import AIInlineCompleter
        client = FakeClient()
        sc = _editor()
        c = AIInlineCompleter(sc, client)
        c.set_enabled(True)
        sc.setCursorPosition(2, 4)
        c.request_now(force=True)
        _wait(qapp, lambda: not c._busy)
        assert "def f(x)" in client.calls[0]["prompt"]
        assert "y = x * 2" in client.calls[0]["prompt"]

    def test_uses_tiny_token_tier(self, qapp):
        """补全只输出一行，不该用大预算"""
        from core.ai_client import TOKEN_TIERS
        from ui.ai_inline_completer import AIInlineCompleter
        client = FakeClient()
        sc = _editor()
        c = AIInlineCompleter(sc, client)
        c.set_enabled(True)
        sc.setCursorPosition(2, 4)
        c.request_now(force=True)
        _wait(qapp, lambda: not c._busy)
        assert client.calls[0]["max_tokens"] == TOKEN_TIERS["tiny"]

    def test_cleaning_strips_code_fence_and_multiline(self, qapp):
        from ui.ai_inline_completer import AIInlineCompleter
        fence = "`" * 3
        # 无语言标记
        assert AIInlineCompleter._clean(fence + "\nreturn 1\n" + fence) == "return 1"
        # 带语言标记 —— 最容易出错的形态：
        # 若先把 ``` 全 replace 掉再取首行，会返回 "python"
        assert AIInlineCompleter._clean(
            fence + "python\nreturn 1\n" + fence) == "return 1"
        assert AIInlineCompleter._clean(
            fence + "javascript\nconst a = 1\n" + fence) == "const a = 1"
        # 围栏内先有空行
        assert AIInlineCompleter._clean(
            fence + "\n\n\nreturn 9\n" + fence) == "return 9"
        # 前缀与多行
        assert AIInlineCompleter._clean("继续：return 1") == "return 1"
        assert AIInlineCompleter._clean("补全：return 1") == "return 1"
        assert AIInlineCompleter._clean("return 1\n多余第二行") == "return 1"
        # 边界
        assert AIInlineCompleter._clean("") == ""
        assert AIInlineCompleter._clean(None) == ""
        assert AIInlineCompleter._clean("return 1") == "return 1"
        assert AIInlineCompleter._clean("  return 1  ") == "return 1"

    def test_language_tag_detection(self):
        from ui.ai_inline_completer import is_language_tag
        for tag in ("python", "javascript", "c++", "c#", "go", "rust",
                    "typescript", "PYTHON", " bash "):
            assert is_language_tag(tag) is True, tag
        # 真正的代码行不能被误判成语言标记
        for code in ("return 1", "x = 1", "def f():", "", "   "):
            assert is_language_tag(code) is False, code

    def test_result_only_first_line_shown(self, qapp):
        from ui.ai_inline_completer import AIInlineCompleter
        sc = _editor()
        c = AIInlineCompleter(sc, FakeClient("return 1\n第二行"))
        c.set_enabled(True)
        sc.setCursorPosition(2, 4)
        c.request_now(force=True)
        assert _wait(qapp, lambda: c.has_suggestion())
        assert c.get_suggestion() == "return 1"


# =========================================================
# 接受 / 清除 / 取消
# =========================================================

class TestAcceptClearCancel:
    def test_accept_inserts_at_cursor(self, qapp):
        from ui.ai_inline_completer import AIInlineCompleter
        sc = _editor()
        c = AIInlineCompleter(sc, FakeClient("return x + 1"))
        c.set_enabled(True)
        sc.setCursorPosition(2, 4)
        c.request_now(force=True)
        _wait(qapp, lambda: c.has_suggestion())
        assert c.accept_suggestion() is True
        assert sc.text() == "def f(x):\n    y = x * 2\n    return x + 1"
        assert c.has_suggestion() is False

    def test_accept_without_suggestion_is_noop(self, qapp):
        from ui.ai_inline_completer import AIInlineCompleter
        sc = _editor()
        c = AIInlineCompleter(sc, FakeClient())
        before = sc.text()
        assert c.accept_suggestion() is False
        assert sc.text() == before

    def test_insert_is_undoable(self, qapp):
        """插入必须走 Scintilla（可 Ctrl+Z 撤销），不能直接改 Python 字符串"""
        from ui.ai_inline_completer import AIInlineCompleter
        sc = _editor()
        sc.SendScintilla(sc.SCI_EMPTYUNDOBUFFER)
        c = AIInlineCompleter(sc, FakeClient("XYZ"))
        c.set_enabled(True)
        sc.setCursorPosition(2, 4)
        c.request_now(force=True)
        _wait(qapp, lambda: c.has_suggestion())
        before = sc.text()
        c.accept_suggestion()
        assert sc.text() != before
        sc.undo()
        assert sc.text() == before, "接受建议应可撤销"

    def test_clear_removes_annotation(self, qapp):
        from ui.ai_inline_completer import AIInlineCompleter
        sc = _editor()
        c = AIInlineCompleter(sc, FakeClient())
        c.set_enabled(True)
        sc.setCursorPosition(2, 4)
        c.request_now(force=True)
        _wait(qapp, lambda: c.has_suggestion())
        c.clear_suggestion()
        assert c.has_suggestion() is False

    def test_cancel_invalidates_inflight(self, qapp):
        """取消后，迟到的响应必须被丢弃（序号机制）"""
        from ui.ai_inline_completer import AIInlineCompleter
        sc = _editor()
        c = AIInlineCompleter(sc, FakeClient("迟到的建议", delay=0.3))
        c.set_enabled(True)
        sc.setCursorPosition(2, 4)
        c.request_now(force=True)
        c.cancel()
        time.sleep(0.5)
        qapp.processEvents()
        assert c.has_suggestion() is False, "取消后不应显示迟到的建议"
        assert c._busy is False

    def test_failure_does_not_raise_or_show(self, qapp):
        """补全失败应静默（不该在编辑器里弹错误）"""
        from ui.ai_inline_completer import AIInlineCompleter
        sc = _editor()
        c = AIInlineCompleter(sc, FakeClient(fail=True))
        c.set_enabled(True)
        sc.setCursorPosition(2, 4)
        c.request_now(force=True)
        assert _wait(qapp, lambda: not c._busy)
        assert c.has_suggestion() is False

    def test_busy_reset_after_completion(self, qapp):
        """_busy 必须复位，否则后续请求全被拒（原实现的跨线程 bug 症状）"""
        from ui.ai_inline_completer import AIInlineCompleter
        sc = _editor()
        c = AIInlineCompleter(sc, FakeClient())
        c.set_enabled(True)
        sc.setCursorPosition(2, 4)
        c.request_now(force=True)
        assert _wait(qapp, lambda: not c._busy), "_busy 未复位"
        assert c.request_now(force=True) is True, "应能再次请求"


# =========================================================
# 编辑器适配
# =========================================================

class TestEditorResolution:
    def test_accepts_plain_scintilla(self, qapp):
        from ui.ai_inline_completer import AIInlineCompleter
        sc = _editor()
        c = AIInlineCompleter(sc, FakeClient())
        assert c.editor is sc

    def test_accepts_wrapper_with_sc_attr(self, qapp):
        """EditorWidget 持有 .sc；补全器应自动取内层控件"""
        from ui.ai_inline_completer import AIInlineCompleter

        class Wrapper:
            def __init__(self, sc):
                self.sc = sc

        sc = _editor()
        c = AIInlineCompleter(Wrapper(sc), FakeClient())
        assert c.editor is sc

    def test_none_editor_is_tolerated(self, qapp):
        from ui.ai_inline_completer import AIInlineCompleter
        c = AIInlineCompleter(None, FakeClient())
        c.set_enabled(True)
        assert c.request_now() is False
        c.clear_suggestion()          # 不应抛异常
        assert c.accept_suggestion() is False
