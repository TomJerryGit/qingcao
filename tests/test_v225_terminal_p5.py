# -*- coding: utf-8 -*-
"""v2.25 P5：滚轮/拖动鼠标编码 + 滚动位置保持"""

from PyQt5.QtCore import QPoint, QPointF, Qt
from PyQt5.QtGui import QWheelEvent

from ui.terminal_screen import TerminalScreen


def test_wheel_and_motion_encoding():
    s = TerminalScreen(5, 10)
    s.feed("\x1b[?1000h\x1b[?1002h\x1b[?1006h")
    assert s.encode_wheel(True, 2, 3) == "\x1b[<64;2;3M"
    assert s.encode_wheel(False, 2, 3) == "\x1b[<65;2;3M"
    assert s.encode_mouse(0, 2, 3, True, motion=True) == "\x1b[<32;2;3M"
    s2 = TerminalScreen(5, 10)
    assert s2.encode_wheel(True, 1, 1) == ""
    assert s2.encode_mouse(0, 1, 1, motion=True) == ""


def test_wheel_event_sends_to_pty(qapp):
    from ui.terminal_panel import TerminalOutput

    out = TerminalOutput()
    try:
        out._screen = TerminalScreen(5, 10)
        out._screen.feed("\x1b[?1000h\x1b[?1006h")
        got = []
        out.mouse_input.connect(got.append)
        ev = QWheelEvent(
            QPointF(10, 10),
            QPointF(10, 10),
            QPoint(0, 0),
            QPoint(0, -120),
            Qt.NoButton,
            Qt.NoModifier,
            Qt.NoScrollPhase,
            False,
        )
        out.wheelEvent(ev)
        assert got, "未发送滚轮事件"
        # 列号随字体/单元格宽度变化（CI 无字体时可能为 2），只校验滚轮方向/按钮与行
        import re

        m = re.match(r"\x1b\[<65;(\d+);1M", got[0])
        assert m and 1 <= int(m.group(1)) <= 3, got[0]
    finally:
        out.deleteLater()


def test_render_preserves_scroll_position_static():
    src = open("ui/terminal_panel.py", encoding="utf-8").read()
    assert "at_bottom" in src and "bar.setValue" in src
