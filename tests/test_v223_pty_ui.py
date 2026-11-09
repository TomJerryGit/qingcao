# -*- coding: utf-8 -*-
"""v2.23：终端 PTY 交互模式 UI 集成"""

import sys
import time

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest


pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="仅 Windows PTY")


def _pump_until(qapp, cond, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.05)
        if cond():
            return True
    return False


def test_pty_tab_echo(qapp):
    pytest.importorskip("winpty")
    from ui.terminal_panel import TerminalPanel

    panel = TerminalPanel(None)
    try:
        tab = panel.add_tab(pty=True)
        assert getattr(tab, "kind", "") == "pty", type(tab).__name__
        panel.input.setText("echo qc-pty-ui")
        panel.run_command()
        assert _pump_until(qapp, lambda: "qc-pty-ui" in panel.output.toPlainText()), (
            panel.output.toPlainText()[-200:]
        )
    finally:
        panel.close()


def test_pty_ctrl_c_interrupt(qapp):
    pytest.importorskip("winpty")
    from ui.terminal_panel import TerminalPanel

    panel = TerminalPanel(None)
    try:
        tab = panel.add_tab(pty=True)
        QTest.keyClick(panel.input, Qt.Key_C, Qt.ControlModifier)
        assert tab.interrupts == 1
    finally:
        panel.close()


def test_pty_fallback_without_winpty(qapp, monkeypatch):
    import ui.terminal_panel as tp

    monkeypatch.setattr(tp, "HAS_WINPTY", False)
    panel = tp.TerminalPanel(None)
    try:
        tab = panel.add_tab(pty=True)
        assert getattr(tab, "kind", "") == "oneshot"
        assert "回退" in panel.tabs.tabText(panel.tabs.currentIndex())
    finally:
        panel.close()
