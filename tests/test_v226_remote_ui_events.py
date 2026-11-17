# -*- coding: utf-8 -*-
"""v2.26 阶段 C：远程 UI 事件回传队列"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_remote_ui_event_queue(qapp):
    from PyQt5.QtWidgets import QMainWindow

    from ui.isolated_plugins import WindowHostAPI

    win = QMainWindow()
    api = WindowHostAPI(win)
    try:
        assert api.enqueue_remote_ui_event(1, "send", "click", "")
        events = api.poll_remote_ui_events()
        assert events and events[0]["id"] == "send"
        assert api.poll_remote_ui_events() == []
    finally:
        win.close()
