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


def test_session_persistence_and_export(tmp_path):
    from core.ai_service import AIService

    path = tmp_path / "sessions.json"
    svc = AIService(client=_Client(), history_path=str(path))
    svc.run("a", session="s1")
    assert path.is_file()
    svc2 = AIService(client=_Client(), history_path=str(path))
    assert "s1" in svc2.session_names()
    export = tmp_path / "export.json"
    assert svc2.export_sessions(str(export))["ok"]
    svc3 = AIService(client=_Client(), history_path=str(tmp_path / "other.json"))
    assert svc3.import_sessions(str(export))["ok"]
    assert "s1" in svc3.session_names()


def test_panel_export_import_buttons(qapp):
    from core.ai_service import AIService, set_ai_service
    from ui.ai_host_panel import AIHostPanel

    service = AIService(client=_Client())
    set_ai_service(service)
    panel = AIHostPanel()
    try:
        assert panel.export_btn is not None and panel.import_btn is not None
    finally:
        set_ai_service(None)
        panel.close()


def test_encrypted_session_roundtrip(tmp_path):
    from cryptography.fernet import Fernet

    from core.ai_service import AIService

    key = Fernet.generate_key().decode("ascii")
    path = tmp_path / "enc.json"
    svc = AIService(client=_Client(), history_path=str(path), encrypt=True, cipher_key=key)
    svc.run("secret-prompt", session="s1")
    raw = path.read_text(encoding="utf-8")
    assert "secret-prompt" not in raw
    svc2 = AIService(client=_Client(), history_path=str(path), encrypt=True, cipher_key=key)
    assert "s1" in svc2.session_names()


def test_import_conflict_policies(tmp_path):
    from core.ai_service import AIService

    export = tmp_path / "e.json"
    source = AIService(client=_Client())
    source.run("x", session="s1")
    source.export_sessions(str(export))

    target = AIService(client=_Client())
    target.run("y", session="s1")
    out = target.import_sessions(str(export), conflict="rename")
    assert out["renamed"] == 1 and "s1 (2)" in target.session_names()

    skipped = AIService(client=_Client())
    skipped.run("y", session="s1")
    out = skipped.import_sessions(str(export), conflict="skip")
    assert out["skipped"] == 1

    overwritten = AIService(client=_Client())
    overwritten.run("y", session="s1")
    out = overwritten.import_sessions(str(export), conflict="overwrite")
    assert out["overwritten"] == 1


def test_preview_import_plan(tmp_path):
    from core.ai_service import AIService

    export = tmp_path / "e.json"
    src = AIService(client=_Client())
    src.run("x", session="s1")
    src.run("y", session="s2")
    src.export_sessions(str(export))

    target = AIService(client=_Client())
    target.run("z", session="s1")
    preview = target.preview_import(str(export), conflict="rename")
    assert preview["ok"]
    assert preview["new"] == ["s2"]
    assert preview["conflicts"][0]["action"] == "rename"
    assert preview["conflicts"][0]["result"] == "s1 (2)"
    # 预览不修改
    assert "s2" not in target.session_names()


def test_search_and_scoped_export(tmp_path):
    from core.ai_service import AIService

    svc = AIService(client=_Client())
    svc.run("alpha", session="s1")
    svc.run("beta", session="s2")
    out = svc.search_sessions("alp")
    assert out["ok"] and out["count"] >= 1
    assert out["matches"][0]["session"] == "s1"

    path = tmp_path / "one.json"
    assert svc.export_sessions(str(path), names=["s2"])["count"] == 1
    imported = AIService(client=_Client())
    imported.import_sessions(str(path))
    assert "s2" in imported.session_names()
    assert "s1" not in imported.session_names()


def test_panel_has_search_and_scope_buttons(qapp):
    from core.ai_service import set_ai_service
    from ui.ai_host_panel import AIHostPanel

    set_ai_service(None)
    panel = AIHostPanel()
    try:
        assert panel.search_edit is not None and panel.search_btn is not None
    finally:
        panel.close()


def test_search_jump_and_highlight(qapp):
    from core.ai_service import AIService, get_ai_service, set_ai_service
    from ui.ai_host_panel import AIHostPanel

    service = AIService(client=_Client())
    service.run("alpha one", session="s1")
    service.run("beta two", session="s2")
    set_ai_service(service)
    panel = AIHostPanel()
    try:
        matches = get_ai_service().search_sessions("alpha")["matches"]
        assert matches and matches[0]["session"] == "s1"
        count = panel.jump_to_match(matches[0], "alpha")
        assert count >= 1
        assert "alpha one" in panel.history_view.toPlainText()
        assert panel.session_combo.currentText() == "s1"
        assert panel.highlight_query("alpha") >= 1
    finally:
        set_ai_service(None)
        panel.close()
