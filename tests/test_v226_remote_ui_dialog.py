# -*- coding: utf-8 -*-
"""v2.26 阶段 C：远程控件对话框"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_remote_ui_dialog_events(qapp):
    from PyQt5.QtWidgets import QMainWindow

    from ui.isolated_plugins import WindowHostAPI

    win = QMainWindow()
    api = WindowHostAPI(win)
    try:
        assert (
            api.show_remote_ui_dialog(
                "AI 结果", {"controls": [{"id": "ok", "kind": "button", "text": "确定"}]}
            )
            == 0
        )
        for _ in range(30):
            qapp.processEvents()
        renderer = api._remote_ui_renderer
        renderer.widget_for("ok").click()
        events = api.poll_remote_ui_events()
        assert events and events[0]["id"] == "ok"
        assert api.update_remote_dialog_controls(
            {"controls": [{"id": "ok", "kind": "button", "text": "完成"}]}
        )
    finally:
        win.close()
