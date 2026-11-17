# -*- coding: utf-8 -*-
"""v2.26：远程面板状态推送（AI 完整 UI 隔离增量）"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_update_remote_panel_text(qapp):
    from PyQt5.QtWidgets import QMainWindow

    from ui.isolated_plugins import WindowHostAPI

    win = QMainWindow()
    api = WindowHostAPI(win)
    try:
        api.register_remote_panel("AI 输出", [], lambda text: "", kind="text")
        for _ in range(50):
            qapp.processEvents()
        pid = next(iter(api.remote_panels))
        assert api.update_remote_panel(pid, "hello") is True
        for _ in range(50):
            qapp.processEvents()
        assert api.remote_panels[pid]["text_widget"].toPlainText() == "hello"
    finally:
        win.close()
