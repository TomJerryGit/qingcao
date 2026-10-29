# -*- coding: utf-8 -*-
"""v2.14.1：插件面板主题冒烟与顺序修复"""
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_theme_apply_order_adapt_before_notify():
    src = open(os.path.join(ROOT, "ui", "main_window.py"),
               encoding="utf-8").read()
    i_adapt = src.find("adapt_widget_styles(self, theme)")
    i_notify = src.find("loader.notify_widgets(self, theme)")
    assert i_adapt != -1 and i_notify != -1
    assert i_adapt < i_notify, "adapt 必须在 notify 之前"


def test_panel_theme_colors_light_dark():
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from ui.plugins_panel import PluginsPanel

    class FakeTheme:
        type = "light"

    class FakeDark:
        type = "dark"

    panel = PluginsPanel()
    try:
        light = panel._theme_colors(FakeTheme())
        dark = panel._theme_colors(FakeDark())
        assert light["bg"].lower() in ("#ffffff", "#fff")
        assert light["fg"].lower() == "#333333"
        assert dark["bg"].lower() in ("#1e1e1e", "#252526")
        assert dark["fg"].lower() == "#d4d4d4"
        qss = panel._build_theme_qss(FakeDark())
        assert "QHeaderView::section" in qss and "QTreeWidget" in qss
    finally:
        panel.close()
