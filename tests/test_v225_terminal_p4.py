# -*- coding: utf-8 -*-
"""v2.25 P4：滚动缓冲 / 24bit 真彩 / 鼠标上报"""

from ui.terminal_screen import TerminalScreen


def test_scrollback_buffer():
    s = TerminalScreen(3, 10)
    s.feed("one\r\ntwo\r\nthree\r\nfour")
    hist = s.scrollback_lines()
    assert hist and hist[0] == "one"


def test_truecolor_sgr():
    s = TerminalScreen(3, 10)
    s.feed("\x1b[38;2;255;100;50mX\x1b[0m")
    out = s.render_html()
    assert "#ff6432" in out
    s2 = TerminalScreen(3, 10)
    s2.feed("\x1b[38;5;196mY")
    assert s2.render_html().count("#") >= 1


def test_mouse_reporting_flag_and_encode():
    s = TerminalScreen(5, 10)
    s.feed("\x1b[?1000h\x1b[?1006h")
    assert 1000 in s.mouse_reporting and 1006 in s.mouse_reporting
    assert s.encode_mouse(0, 3, 2, True) == "\x1b[<0;3;2M"
    assert s.encode_mouse(0, 3, 2, False) == "\x1b[<0;3;2m"
    s.feed("\x1b[?1000l")
    assert 1000 not in s.mouse_reporting
