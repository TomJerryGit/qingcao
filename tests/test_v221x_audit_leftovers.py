# -*- coding: utf-8 -*-
"""v2.21.x 审计遗留：终端菜单/快捷键 + 市场批量更新确认"""

import os

from PyQt5.QtWidgets import QMessageBox


def _make_window(qapp, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))
    from ui.main_window import MainWindow

    return MainWindow()


def test_terminal_in_panel_menu_with_shortcut(qapp, monkeypatch):
    win = _make_window(qapp, monkeypatch)
    try:
        acts = [a for a in win.panel_menu.actions() if a.text() == "终端"]
        assert len(acts) == 1, [a.text() for a in win.panel_menu.actions()]
        assert acts[0].shortcut().isEmpty()  # NPP 窗口菜单会复制面板项
        from PyQt5.QtWidgets import QAction

        shorts = [a for a in win.findChildren(QAction) if a.shortcut().toString() == "Ctrl+Shift+`"]
        assert len(shorts) == 1, [a.text() for a in shorts]
        assert "终端" in shorts[0].text()
        acts[0].setChecked(True)
        assert win._ensure_panel("terminal")
        assert win.terminal is not None
        assert not win.terminal.isHidden()
        acts[0].setChecked(False)
    finally:
        try:
            win.session.save = lambda *a, **k: None
        except Exception:
            pass
        win.close()


def test_batch_update_confirmation(qapp, monkeypatch):
    from ui.plugin_store import PluginInfo, PluginStoreDialog

    dlg = PluginStoreDialog.__new__(PluginStoreDialog)

    class _Lbl:
        def setText(self, *a):
            pass

        def setEnabled(self, *a):
            pass

    dlg.status_label = _Lbl()
    dlg.check_updates_btn = _Lbl()

    class _Client:
        def check_updates(self):
            return [PluginInfo(name="demo", version="2.0.0")]

    dlg.client = _Client()
    calls = []
    dlg._update_all = lambda updates: calls.append(updates)

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    dlg._check_updates()
    assert calls and calls[0][0].name == "demo"

    calls.clear()
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))
    dlg._check_updates()
    assert not calls


def test_static_shortcut_no_conflict():
    import io

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = io.open(
        os.path.join(root, "ui", "mixins", "menu_builder_mixin.py"), encoding="utf-8"
    ).read()
    assert '("终端", "panel.terminal"' in src
    assert "Ctrl+Shift+`" in src
