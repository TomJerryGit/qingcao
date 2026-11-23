# -*- coding: utf-8 -*-
"""内嵌运行控制台：input() 交互"""

import os
import sys
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_run_console_input(qapp, tmp_path):
    from ui.run_console_panel import RunConsolePanel

    script = tmp_path / "ask.py"
    script.write_text("name=input('NAME? ')\nprint('HELLO '+name)\n", encoding="utf-8")
    panel = RunConsolePanel()
    try:
        panel.run_file(str(script))
        for _ in range(100):
            qapp.processEvents()
            time.sleep(0.05)
        panel.input.setText("Bob")
        panel.send_input()
        for _ in range(100):
            qapp.processEvents()
            time.sleep(0.05)
        text = panel.output.toPlainText()
        assert "HELLO Bob" in text, text
    finally:
        panel.stop()
        panel.close()
