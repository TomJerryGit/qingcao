# -*- coding: utf-8 -*-
"""v2.21 P1-1：终端 MVP"""

import glob
import os
import time

from PyQt5.QtCore import QProcess


def _pump(qapp, panel, timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if panel._proc is None:
            return True
        time.sleep(0.02)
    return False


def test_execute_echo(qapp):
    from ui.terminal_panel import TerminalPanel

    panel = TerminalPanel(None)
    try:
        panel.input.setText("echo qc-terminal-ok")
        panel.run_command()
        assert _pump(qapp, panel), "命令未在超时内完成"
        assert "qc-terminal-ok" in panel.output.toPlainText()
        assert "退出码 0" in panel.output.toPlainText()
    finally:
        panel.close()


def test_cd_and_clear(qapp, tmp_path):
    from ui.terminal_panel import TerminalPanel

    panel = TerminalPanel(None)
    try:
        panel.input.setText('cd "%s"' % tmp_path)
        panel.run_command()
        assert os.path.abspath(str(tmp_path)) == panel._cwd
        panel.clear_output()
        assert panel.output.toPlainText() == ""
    finally:
        panel.close()


def test_wiring_static():
    import io

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mw = io.open(os.path.join(root, "ui", "main_window.py"), encoding="utf-8").read()
    assert "terminal" in mw
    reg = io.open(
        os.path.join(root, "ui", "mixins", "panel_registry_mixin.py"), encoding="utf-8"
    ).read()
    assert "_build_panel_terminal" in reg
    cap = "".join(
        open(p, encoding="utf-8").read()
        for p in glob.glob(os.path.join(root, "ui", "mixins", "capability_*.py"))
    )
    assert "_toggle_terminal" in cap
    mb = io.open(
        os.path.join(root, "ui", "mixins", "menu_builder_mixin.py"), encoding="utf-8"
    ).read()
    assert "panel.terminal" in mb and "Ctrl+Shift+`" in mb
    assert os.path.isfile(os.path.join(root, "docs", "terminal_mvp.md"))
    assert QProcess is not None
