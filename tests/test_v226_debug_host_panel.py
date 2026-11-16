# -*- coding: utf-8 -*-
"""v2.26 B3-D5：调试器宿主面板"""

import os

from PyQt5.QtCore import QObject, pyqtSignal


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _Service(QObject):
    event = pyqtSignal(dict)


def test_panel_updates_from_events(qapp):
    from ui.debug_host_panel import DebugHostPanel

    service = _Service()
    panel = DebugHostPanel(service)
    try:
        service.event.emit({"event": "debug.break", "data": {"file": "a.py", "line": 4}})
        assert "a.py" in panel.status.text() and ":5" in panel.status.text()
        service.event.emit(
            {
                "event": "debug.stack",
                "data": {"frames": [{"name": "fn", "file": "a.py", "line": 5}]},
            }
        )
        assert panel.stack_tree.topLevelItemCount() == 1
        service.event.emit({"event": "debug.locals", "data": {"values": {"x": 1, "y": "s"}}})
        assert panel.locals_tree.topLevelItemCount() == 2
        service.event.emit({"event": "debug.exit", "data": {"code": 0}})
        assert "已结束" in panel.status.text()
    finally:
        panel.close()


def test_panel_exists_in_ui():
    assert os.path.isfile(os.path.join(ROOT, "ui", "debug_host_panel.py"))
