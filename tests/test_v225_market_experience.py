# -*- coding: utf-8 -*-
"""v2.25 市场体验：评分筛选 / 更新公告 / 版本对比"""

import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _P:
    def __init__(self, name="demo", **kw):
        self.name = name
        for k, v in kw.items():
            setattr(self, k, v)


def test_plugin_rating_score_priority():
    from ui.plugin_store import plugin_rating_score

    p = _P("demo")
    assert plugin_rating_score(p, lambda n: (4.5, 2), {}) == (4.5, 2)
    assert plugin_rating_score(p, lambda n: None, {"demo": {"stars": 3}}) == (3.0, 1)
    assert plugin_rating_score(p, lambda n: None, {}) == (0.0, 0)


def test_passes_rating_filter_modes():
    from ui.plugin_store import passes_rating_filter

    assert passes_rating_filter((4.5, 2), "all") is True
    assert passes_rating_filter((4.5, 2), "4") is True
    assert passes_rating_filter((3.5, 2), "4") is False
    assert passes_rating_filter((0.0, 0), "none") is True
    assert passes_rating_filter((4.0, 1), "none") is False


def test_update_count_and_version_comparison():
    from ui.plugin_client import PluginInfo, PluginState
    from ui.plugin_detail import version_comparison_text
    from ui.plugin_store import update_count

    a = PluginInfo(
        name="a", version="1.2.0", installed_version="1.1.0", state=PluginState.UPDATE_AVAILABLE
    )
    b = PluginInfo(
        name="b", version="1.0.0", installed_version="1.0.0", state=PluginState.INSTALLED
    )
    c = PluginInfo(name="c", version="2.0.0")
    assert update_count([a, b, c]) == 1
    assert "可更新" in version_comparison_text(a)
    assert "已是最新" in version_comparison_text(b)
    assert version_comparison_text(c) == ""


def test_update_banner_visibility(qapp):
    from PyQt5.QtCore import Qt

    from ui.plugin_client import PluginInfo, PluginState
    from ui.plugin_store import PluginStoreDialog

    dlg = PluginStoreDialog()
    try:
        dlg._all_plugins = []
        dlg._refresh_update_banner()
        assert dlg.update_banner.isHidden() is True
        dlg._all_plugins = [PluginInfo(name="a", state=PluginState.UPDATE_AVAILABLE)]
        dlg._refresh_update_banner()
        assert dlg.update_banner.isHidden() is False
        assert "1" in dlg.update_label.text()
    finally:
        dlg.close()
