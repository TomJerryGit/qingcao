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

        # 等待 shell 提示符/启动横幅出现后再输入，避免慢机器上命令早于 PTY 就绪
        def _shell_ready():
            screen = getattr(tab, "_screen", None)
            text = (screen.text() if screen is not None else "") + panel.output.toPlainText()
            return ">" in text or "$" in text

        assert _pump_until(qapp, _shell_ready, timeout=30), "PTY 未就绪"
        panel.input.setText("echo qc-pty-ui")
        panel.run_command()

        def _echo_seen():
            # 输出区为 HTML 渲染；同时校验屏幕缓冲区，避免不同平台 toPlainText 差异
            if "qc-pty-ui" in panel.output.toPlainText():
                return True
            screen = getattr(tab, "_screen", None)
            return bool(screen and "qc-pty-ui" in screen.text())

        assert _pump_until(qapp, _echo_seen, timeout=30), panel.output.toPlainText()[-200:]
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
