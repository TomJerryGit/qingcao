# -*- coding: utf-8 -*-
"""v2.25 终端原始模式 P1：按键→PTY 字节映射 + raw 开关"""


def test_key_event_to_bytes(qapp):
    from PyQt5.QtCore import QEvent, Qt
    from PyQt5.QtGui import QKeyEvent

    from ui.terminal_panel import key_event_to_bytes

    def ev(key, text="", mods=Qt.NoModifier):
        return QKeyEvent(QEvent.KeyPress, key, mods, text)

    assert key_event_to_bytes(ev(Qt.Key_Return)) == "\r"
    assert key_event_to_bytes(ev(Qt.Key_Backspace)) == "\x7f"
    assert key_event_to_bytes(ev(Qt.Key_Up)) == "\x1b[A"
    assert key_event_to_bytes(ev(Qt.Key_Escape)) == "\x1b"
    assert key_event_to_bytes(ev(Qt.Key_A, "a")) == "a"
    assert key_event_to_bytes(ev(Qt.Key_C, "", Qt.ControlModifier)) == "\x03"


def test_raw_line_edit_emits_bytes(qapp, monkeypatch):
    from PyQt5.QtCore import QEvent, Qt
    from PyQt5.QtGui import QKeyEvent

    from ui.terminal_panel import PtyLineEdit

    edit = PtyLineEdit()
    got = []
    edit.raw_key.connect(got.append)
    edit.raw_mode = True
    edit.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.NoModifier, "a"))
    edit.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
    assert got == ["a", "\r"]
    edit.raw_mode = False
    edit.deleteLater()
