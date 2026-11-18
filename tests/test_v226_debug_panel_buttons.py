# -*- coding: utf-8 -*-
"""v2.26 P1：DebugHostPanel 按钮动作 e2e"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _Svc:
    def __init__(self):
        self.calls = []

    def handle(self, command, *a, **k):
        self.calls.append(command)


def test_debug_panel_buttons(qapp):
    from ui.debug_host_panel import DebugHostPanel

    svc = _Svc()
    panel = DebugHostPanel(svc)
    try:
        for btn, cmd in (
            (panel.continue_btn, "debug.continue"),
            (panel.pause_btn, "debug.pause"),
            (panel.over_btn, "debug.over"),
            (panel.stop_btn, "debug.stop"),
        ):
            btn.click()
            assert cmd in svc.calls
    finally:
        panel.close()
