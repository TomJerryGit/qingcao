# -*- coding: utf-8 -*-
"""v2.20 P1-3：插件市场本地评分 MVP"""

import io
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_local_ratings_store(tmp_path, monkeypatch):
    monkeypatch.setenv("QINGCAO_PLUGIN_RATINGS_FILE", str(tmp_path / "ratings.json"))
    from ui.plugin_rating import LocalRatings, rating_text

    store = LocalRatings()
    assert store.get("demo") is None
    store.set_rating("demo", 4, "很好用")
    assert store.get("demo")["stars"] == 4
    assert store.get("demo")["comment"] == "很好用"
    reloaded = LocalRatings()
    assert reloaded.get("demo")["stars"] == 4
    assert reloaded.all()["demo"]["stars"] == 4
    assert rating_text(4).startswith("★★★★☆")
    assert reloaded.remove("demo") is True
    assert reloaded.get("demo") is None


def test_detail_rating_ui(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("QINGCAO_PLUGIN_RATINGS_FILE", str(tmp_path / "r2.json"))
    from ui.plugin_store import PluginDetailDialog, PluginInfo

    info = PluginInfo(name="demo", display_name="Demo", version="1.0.0")
    dlg = PluginDetailDialog(info)
    try:
        assert len(dlg.star_buttons) == 5
        dlg._set_local_stars(5)
        dlg._save_local_rating()
        assert "已保存" in dlg.rating_status.text()
        from ui.plugin_rating import LocalRatings

        assert LocalRatings().get("demo")["stars"] == 5
    finally:
        dlg.close()


def test_sort_option_wired():
    src = io.open(os.path.join(ROOT, "ui", "plugin_store.py"), encoding="utf-8").read()
    assert '("local_rating"' in src
    assert "_build_rating_widget" in src


def test_docs():
    assert os.path.isfile(os.path.join(ROOT, "docs", "plugin_rating_mvp.md"))
