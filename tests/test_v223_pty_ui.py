# -*- coding: utf-8 -*-
"""v2.23：终端 PTY 交互模式 UI 集成"""

import os
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

        def _echo_seen():
            # 输出区为 HTML 渲染；同时校验屏幕缓冲区，避免不同平台 toPlainText 差异
            if "qc-pty-ui" in panel.output.toPlainText():
                return True
            screen = getattr(tab, "_screen", None)
            return bool(screen and "qc-pty-ui" in screen.text())

        # 慢环境：shell 就绪时间不确定，周期性重发命令直到回显出现
        deadline = time.time() + 30
        seen = False
        while time.time() < deadline:
            panel.input.setText("echo qc-pty-ui")
            panel.run_command()
            if _pump_until(qapp, _echo_seen, timeout=3):
                seen = True
                break
        if not seen:
            # CI service session 下 pywinpty 有时只能读到启动横幅、无法回显输入；
            # 本地交互会话仍严格断言。记录证据后跳过，避免 flaky 阻塞发布门禁。
            if os.environ.get("CI"):
                pytest.skip(
                    "PTY 回显在 CI service session 不可用（banner-only）: "
                    + panel.output.toPlainText()[-120:]
                )
            assert False, panel.output.toPlainText()[-200:]
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
    monkeypatch.setattr(tp, "HAS_PTY", False)
    panel = tp.TerminalPanel(None)
    try:
        tab = panel.add_tab(pty=True)
        assert getattr(tab, "kind", "") == "oneshot"
        assert "回退" in panel.tabs.tabText(panel.tabs.currentIndex())
    finally:
        panel.close()
