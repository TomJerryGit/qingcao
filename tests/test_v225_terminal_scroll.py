# -*- coding: utf-8 -*-
"""v2.25 P3：滚动区（CSI r / S / T / L / M）"""

from ui.terminal_screen import TerminalScreen


def test_scroll_region_linefeed():
    s = TerminalScreen(6, 12)
    s.feed("\x1b[2;4r")  # 区域第 2-4 行
    s.feed("\x1b[4;1Hbottom")
    before = s.text()
    s.feed("\n")
    after = s.text()
    # 只滚动区域内：第 1 行不变
    assert before.splitlines()[0] == after.splitlines()[0]


def test_scroll_up_down_and_reset():
    s = TerminalScreen(4, 10)
    s.feed("A\r\nB\r\nC\r\nD")
    s.feed("\x1b[2;3r")
    s.feed("\x1b[S")  # 区域上滚一行
    lines = s.text().splitlines()
    assert lines[0] == "A"
    s.feed("\x1b[r")
    assert (s.scroll_top, s.scroll_bottom) == (0, 3)


def test_insert_delete_line():
    s = TerminalScreen(5, 10)
    s.feed("one\r\ntwo\r\nthree")
    s.feed("\x1b[2;1H\x1b[L")  # 第2行插入空行
    assert s.text().splitlines()[1].strip() == ""
    s.feed("\x1b[M")
    assert "two" in s.text()
