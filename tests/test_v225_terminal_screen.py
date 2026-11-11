# -*- coding: utf-8 -*-
"""v2.25 P2：ANSI/VT 屏幕模拟（alt-screen/光标/清屏/颜色）"""

from ui.terminal_screen import TerminalScreen


def test_text_clear_and_cursor():
    s = TerminalScreen(5, 20)
    s.feed("hello")
    assert s.text().splitlines()[0].startswith("hello")
    s.feed("\r\nworld")
    assert "world" in s.text()
    s.feed("\x1b[1;1HXY")
    assert s.text().splitlines()[0].startswith("XYllo")
    s.feed("\x1b[2J")
    assert s.text().strip() == ""


def test_alt_screen_roundtrip():
    s = TerminalScreen(5, 20)
    s.feed("main")
    s.feed("\x1b[?1049h")
    s.feed("ALT")
    assert "ALT" in s.text() and "main" not in s.text()
    assert s.alt is True
    s.feed("\x1b[?1049l")
    assert s.alt is False
    assert s.text().startswith("main")


def test_sgr_color_html():
    s = TerminalScreen(3, 20)
    s.feed("\x1b[31mred\x1b[0m")
    import re

    out = s.render_html()
    assert "color:#cd3131" in out
    assert "red" in re.sub(r"<[^>]+>", "", out)
