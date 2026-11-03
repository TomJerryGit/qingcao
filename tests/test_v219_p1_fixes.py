# -*- coding: utf-8 -*-
"""v2.19 P1 修复：主题菜单 / 设置 UI / F5 共享动作"""

import io
import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _FakePrefs:
    def __init__(self, data=None):
        self.data = dict(data or {})
        self.written = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.written[key] = value


def _builtin_theme_display_names():
    names = []
    for f in sorted(os.listdir(os.path.join(ROOT, "themes"))):
        if not f.endswith(".json"):
            continue
        data = json.load(io.open(os.path.join(ROOT, "themes", f), encoding="utf-8"))
        names.append(data.get("display_name") or os.path.splitext(f)[0])
    return names


def test_theme_menu_lists_builtin_themes(qapp, monkeypatch):
    from PyQt5.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Ok))
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        texts = [a.text() for a in win.theme_menu.actions()]
        for name in _builtin_theme_display_names():
            assert name in texts, "主题菜单缺少: %s (实际: %s)" % (name, texts)
        assert "跟随系统" in texts
    finally:
        try:
            win.session.save = lambda *a, **k: None
        except Exception:
            pass
        win.close()


def test_f5_unique_action(qapp, monkeypatch):
    from PyQt5.QtWidgets import QAction, QMessageBox

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Ok))
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        acts = [a for a in win.findChildren(QAction) if a.shortcut().toString() == "F5"]
        assert len(acts) == 1, "F5 应只有一个 QAction（多菜单复用）: %d" % len(acts)
    finally:
        try:
            win.session.save = lambda *a, **k: None
        except Exception:
            pass
        win.close()


def test_editor_page_large_file_settings(qapp):
    from ui.preferences_panel import EditorPage

    page = EditorPage(_FakePrefs({"large_file_threshold": 20}))
    try:
        assert page.large_file_threshold_spin.value() == 20
        fake = _FakePrefs({"mmap_incremental_save": True, "large_file_threshold": 20})
        page.prefs = fake
        page.mmap_save_cb.setChecked(False)
        page.large_file_threshold_spin.setValue(64)
        page.apply()
        assert fake.written["mmap_incremental_save"] is False
        assert fake.written["large_file_threshold"] == 64
    finally:
        page.deleteLater()


def test_advanced_page_live_diagnostics(qapp):
    from ui.preferences_panel import AdvancedPage

    fake = _FakePrefs({"live_diagnostics_max_mb": 8})
    page = AdvancedPage(fake)
    try:
        assert page.live_diag_spin.value() == 8
        page.live_diag_spin.setValue(32)
        page.apply()
        assert fake.written["live_diagnostics_max_mb"] == 32
    finally:
        page.deleteLater()


def test_registry_token_ui_static():
    src = io.open(os.path.join(ROOT, "ui", "plugin_store.py"), encoding="utf-8").read()
    assert "registry_token_edit" in src
    assert "registry_tls_cb" in src
    assert 'setValue("registry_token"' in src
    assert "registry_verify_tls" in src
