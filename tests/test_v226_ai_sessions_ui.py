# -*- coding: utf-8 -*-
"""v2.26：AI 会话重命名/删除"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _Client:
    def chat(self, prompt, system="", messages=None, use_history=False, **kwargs):
        return "ok"


def test_session_rename_and_delete():
    from core.ai_service import AIService

    svc = AIService(client=_Client())
    svc.run("a", session="s1")
    svc.run("b", session="default")
    assert svc.rename_session("s1", "renamed")["ok"]
    assert "renamed" in svc.session_names()
    assert "s1" not in svc.session_names()
    assert svc.rename_session("renamed", "default")["ok"] is False
    assert svc.delete_session("renamed")["ok"]
    assert svc.delete_session("missing")["ok"] is False


def test_panel_rename_delete_buttons(qapp, monkeypatch):
    from PyQt5.QtWidgets import QInputDialog, QMessageBox

    from core.ai_service import AIService, set_ai_service
    from ui.ai_host_panel import AIHostPanel

    service = AIService(client=_Client())
    service.set_current_session("old")
    set_ai_service(service)
    panel = AIHostPanel()
    try:
        assert panel.session_combo.currentText() == "old"
        assert panel.rename_btn is not None and panel.delete_btn is not None
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("new", True))
        panel._rename_session()
        assert "new" in [
            panel.session_combo.itemText(i) for i in range(panel.session_combo.count())
        ]
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
        panel._delete_session()
        assert "new" not in service.session_names()
    finally:
        set_ai_service(None)
        panel.close()
