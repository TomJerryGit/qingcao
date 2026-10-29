# -*- coding: utf-8 -*-
"""v2.15 P1：问题面板过滤/清除 + 实例上限设置 + 市场本地目录"""
import os

from PyQt5.QtCore import QSettings


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _close(win):
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()


def test_market_catalog_from_manifests():
    from ui.plugin_store import build_market_catalog
    catalog = build_market_catalog(os.path.join(ROOT, "plugins"))
    assert isinstance(catalog, dict)
    plugins = catalog.get("plugins") or []
    assert len(plugins) >= 13
    names = {p["name"] for p in plugins}
    assert "ai_assistant" in names and "spell_check" in names
    for p in plugins:
        for key in ("category", "license", "homepage", "keywords"):
            assert key in p, (p["name"], key)


def test_problems_filter_and_clear_sandbox(qapp):
    from core.problems import Problem, get_problem_manager
    from ui.main_window import MainWindow
    from ui.problems_panel import ProblemsPanel
    manager = get_problem_manager()
    manager.clear()
    fp = os.path.join(ROOT, "tests", "fixture_v215.py")
    manager.set_file_problems(fp, [
        Problem(filepath=fp, line=0, col=0, severity="info",
                message="sandbox-msg", source="sandbox:dummy"),
        Problem(filepath=fp, line=1, col=0, severity="error",
                message="lsp-msg", source="lsp:pylsp"),
    ])
    win = MainWindow()
    panel = ProblemsPanel(main_window=win)
    try:
        panel.refresh()
        assert panel.tree.topLevelItemCount() == 1
        assert panel.tree.topLevelItem(0).childCount() == 2

        panel.filter_combo.setCurrentIndex(1)  # 仅沙箱
        panel.refresh()
        assert panel.tree.topLevelItem(0).childCount() == 1
        assert panel.tree.topLevelItem(0).child(0).text(1) == "sandbox-msg"

        panel.filter_combo.setCurrentIndex(2)  # 仅非沙箱
        panel.refresh()
        assert panel.tree.topLevelItem(0).childCount() == 1
        assert panel.tree.topLevelItem(0).child(0).text(1) == "lsp-msg"

        removed = win.clear_sandbox_problems()
        assert removed == 1
        remain = manager.get_for_file(fp)
        assert len(remain) == 1 and remain[0].source == "lsp:pylsp"
    finally:
        manager.clear()
        panel.close()
        _close(win)


def test_instance_cap_spinbox_and_apply(qapp):
    from unittest.mock import patch

    from ui.preferences_panel import GeneralPage

    class FakePrefs:
        def __init__(self):
            self.data = {}

        def get(self, key, default=None):
            return self.data.get(key, default)

        def set(self, key, value):
            self.data[key] = value

    class FakeSettings:
        saved = {}

        def __init__(self, *a, **k):
            pass

        def setValue(self, key, value):
            FakeSettings.saved[key] = value

        def sync(self):
            pass

    page = GeneralPage(FakePrefs())
    try:
        assert page.max_instances_spin.minimum() == 1
        assert page.max_instances_spin.maximum() == 10
        page.max_instances_spin.setValue(7)
        with patch("ui.preferences_panel.QSettings", FakeSettings):
            page.apply()
        assert FakeSettings.saved.get("max_new_window_instances") == 7
    finally:
        page.close()


def test_fallback_uses_local_catalog():
    src = open(os.path.join(ROOT, "ui", "plugin_store.py"),
               encoding="utf-8").read()
    assert "def build_market_catalog" in src
    assert "build_market_catalog(" in src.split("_load_fallback_registry", 1)[1]