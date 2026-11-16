# -*- coding: utf-8 -*-
"""v2.26 P4：市场收藏 + 插件对比"""

import os
import types

from PyQt5.QtCore import QSettings


def test_favorites_persistence(tmp_path):
    from ui.plugin_favorites import is_favorite, load_favorites, toggle_favorite

    settings = QSettings(str(tmp_path / "m.ini"), QSettings.IniFormat)
    assert load_favorites(settings) == set()
    assert toggle_favorite("demo", settings) is True
    assert is_favorite("demo", settings)
    assert load_favorites(settings) == {"demo"}
    assert toggle_favorite("demo", settings) is False
    assert load_favorites(settings) == set()


def test_compare_rows_fields():
    from ui.plugin_compare import compare_rows

    left = types.SimpleNamespace(
        version="1.0",
        author="A",
        type="tool",
        permissions=["editor_read"],
        rating=4.5,
        security="low",
        status="enabled",
        description="left",
    )
    right = types.SimpleNamespace(
        version="2.0",
        author="B",
        type="theme",
        permissions=["filesystem", "dialog"],
        rating=3.0,
        security="medium",
        status="disabled",
        description="right",
    )
    rows = compare_rows(left, right)
    labels = [r[0] for r in rows]
    assert "版本" in labels and "权限" in labels
    by = {r[0]: r for r in rows}
    assert by["版本"][1] == "1.0" and by["版本"][2] == "2.0"
    assert "filesystem" in by["权限"][2]


def test_market_ui_has_favorites_and_compare():
    card = open("ui/plugin_store_card.py", encoding="utf-8").read()
    store = open("ui/plugin_store.py", encoding="utf-8").read()
    assert "fav_btn" in card and "toggle_favorite" in card
    assert "favorites_check" in store and "compare_btn" in store
    assert "PluginCompareDialog" in store
