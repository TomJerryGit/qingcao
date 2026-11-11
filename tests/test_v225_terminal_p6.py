# -*- coding: utf-8 -*-
"""v2.25 P6：独立 scrollback 视图 + 渲染节流"""

from PyQt5.QtWidgets import QTextEdit

from ui.terminal_screen import TerminalScreen


def test_history_dialog_shows_scrollback(qapp):
    from ui.terminal_panel import TerminalHistoryDialog

    s = TerminalScreen(3, 20)
    s.feed("history-1\r\nhistory-2\r\nhistory-3\r\nhistory-4")
    dlg = TerminalHistoryDialog(s)
    try:
        text = dlg.view.toPlainText()
        assert "history-1" in text and "history-4" in text
    finally:
        dlg.close()


def test_render_throttle_by_revision():
    from ui.terminal_panel import render_needed

    s = TerminalScreen(5, 20)
    assert render_needed(s, -1) is True
    rev = s.revision
    assert render_needed(s, rev) is False
    s.feed("x")
    assert render_needed(s, rev) is True


def test_screen_revision_increments():
    s = TerminalScreen(3, 10)
    assert s.revision == 0
    s.feed("a")
    assert s.revision == 1
    s.feed("")
    assert s.revision == 1
