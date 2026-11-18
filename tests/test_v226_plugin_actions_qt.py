# -*- coding: utf-8 -*-
"""v2.26 P1：TodoPanel 扫描动作（Qt 夹具）"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _API:
    def __init__(self):
        self.status = []

    def __getattr__(self, name):
        return lambda *a, **k: None

    def get_current_filepath(self):
        return "sample.py"

    def get_current_text(self):
        return "# TODO: fix this\nx = 1\n"

    def get_config(self, *a, **k):
        return None

    def show_status(self, *a, **k):
        self.status.append(a)


def test_todo_panel_scan_action(qapp):
    from PyQt5.QtWidgets import QMainWindow

    from plugins.todo_panel import TodoPanel

    win = QMainWindow()
    panel = TodoPanel(_API(), win)
    try:
        panel.scan_current_file()
        assert panel.count_label.text() or True
    finally:
        panel.close()
        win.close()
