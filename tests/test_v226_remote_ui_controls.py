# -*- coding: utf-8 -*-
"""v2.26 阶段 C：控件面板宿主渲染 + 事件回传"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_controls_panel_event_queue(qapp):
    from PyQt5.QtWidgets import QMainWindow

    from ui.isolated_plugins import WindowHostAPI

    win = QMainWindow()
    api = WindowHostAPI(win)
    try:
        pid = api.register_remote_panel("AI", [], None, kind="controls")
        for _ in range(30):
            qapp.processEvents()
        api.update_remote_controls(
            pid, {"controls": [{"id": "send", "kind": "button", "text": "发送"}]}
        )
        for _ in range(30):
            qapp.processEvents()
        rec = api.remote_panels[pid]
        rec["renderer"].widget_for("send").click()
        events = api.poll_remote_ui_events()
        assert events and events[0]["id"] == "send"
    finally:
        win.close()
