# -*- coding: utf-8 -*-
"""Vim 模式测试（v2 操作符/文本对象/寄存器）"""
import pytest


@pytest.fixture
def vim(qapp):
    """返回一个 Vim 模式实例（用真 QsciScintilla）"""
    try:
        from PyQt5.Qsci import QsciScintilla

        from core.vim_mode import VimMode, VimState
    except ImportError:
        pytest.skip("vim_mode 或 QsciScintilla 不可用")

    editor = QsciScintilla()
    editor.setUtf8(True)
    editor.setText("hello world\nfoo bar\nbaz qux\n")
    # C(v2): 显式设置光标到 (0, 0)
    # setText 后光标位置在不同 Qt/Scintilla 版本下不一致，
    # 可能是末尾或 0。明确指定，避免 dd/yy/dw 操作错行。
    editor.setCursorPosition(0, 0)

    vm = VimMode(editor)
    vm.set_enabled(True)
    return vm, editor, VimState


def _send_key(vim_obj, ch: str):
    """模拟按键"""
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QKeyEvent

    key = Qt.Key_A + (ord(ch.upper()) - ord('A')) if ch.isalpha() else Qt.Key_unknown
    event = QKeyEvent(
        QKeyEvent.KeyPress, key, Qt.NoModifier, ch
    )
    return vim_obj.handle_key(event)


class TestOperators:
    """dw / dd / cw / cc 等"""

    def test_dd_deletes_line(self, vim):
        vm, editor, _ = vim
        # 光标在第 0 行
        _send_key(vm, 'd')
        _send_key(vm, 'd')
        # 第 0 行被删
        text = editor.text()
        assert not text.startswith("hello world")

    def test_yy_yank_and_p_paste(self, vim):
        vm, editor, _ = vim
        vm.registers['"'] = ''
        _send_key(vm, 'y')
        _send_key(vm, 'y')
        # 再 p 粘贴
        _send_key(vm, 'p')
        text = editor.text()
        # 应该有两行 "hello world"
        assert text.count("hello world") >= 2

    def test_dw_deletes_word(self, vim):
        vm, editor, _ = vim
        # 光标在行首
        _send_key(vm, 'd')
        _send_key(vm, 'w')
        text = editor.text()
        # "hello" 应被删除
        assert "hello" not in text

    def test_iw_textobj(self, vim):
        vm, editor, _ = vim
        # 光标在第 0 行 位置 2（"hello" 中间）
        editor.setCursorPosition(0, 2)
        _send_key(vm, 'd')
        _send_key(vm, 'i')
        _send_key(vm, 'w')
        text = editor.text()
        assert "hello" not in text
        # "world" 保留
        assert "world" in text


class TestRegisters:
    """命名寄存器"""

    def test_named_register_yank_paste(self, vim):
        vm, editor, _ = vim
        # "ayy 复制到 a 寄存器
        _send_key(vm, '"')
        _send_key(vm, 'a')
        _send_key(vm, 'y')
        _send_key(vm, 'y')

        # 检查 a 寄存器
        assert 'a' in vm.registers
        assert 'hello' in vm.registers['a']

    def test_register_not_leak(self, vim):
        vm, editor, _ = vim
        # "a" 后跟非法字符 → 应清空 pending
        _send_key(vm, '"')
        # 换行符（不是合法寄存器名）
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QKeyEvent
        event = QKeyEvent(
            QKeyEvent.KeyPress, Qt.Key_Enter, Qt.NoModifier, '\n'
        )
        vm.handle_key(event)
        # 状态应已清空
        assert vm._pending_register is None


class TestTextObjects:
    """文本对象"""

    def test_di_quote(self, vim):
        vm, editor, _ = vim
        editor.setText('say "hello world" end')
        editor.setCursorPosition(0, 8)  # 在 "hello" 内部

        _send_key(vm, 'd')
        _send_key(vm, 'i')
        _send_key(vm, '"')

        text = editor.text()
        # 引号内容被删，引号保留
        assert text == 'say "" end'

    def test_da_quote(self, vim):
        vm, editor, _ = vim
        editor.setText('say "hello world" end')
        editor.setCursorPosition(0, 8)

        _send_key(vm, 'd')
        _send_key(vm, 'a')
        _send_key(vm, '"')

        text = editor.text()
        # 引号 + 内容都被删
        assert text == 'say  end'


class TestSearchRepeat:
    """n / N 查找重复"""

    def test_n_finds_next(self, vim):
        vm, editor, _ = vim
        editor.setText("foo bar foo baz foo")
        editor.setCursorPosition(0, 0)

        vm.last_search = "foo"
        _send_key(vm, 'n')
        pos = editor.SendScintilla(editor.SCI_GETCURRENTPOS)
        # 应该跳到第二个 foo
        assert pos > 0


class TestUnknownMotion:
    """未知动作不应崩溃"""

    def test_dq_no_crash(self, vim):
        """dq（无意义动作）应静默放弃"""
        vm, editor, _ = vim
        _send_key(vm, 'd')
        _send_key(vm, 'q')
        # 状态应被清理
        assert vm._pending_operator is None

    def test_d_escape_no_crash(self, vim):
        """d 后按 Esc"""
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QKeyEvent
        vm, editor, _ = vim
        _send_key(vm, 'd')
        event = QKeyEvent(
            QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier, ''
        )
        vm.handle_key(event)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])