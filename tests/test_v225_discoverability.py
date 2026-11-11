# -*- coding: utf-8 -*-
"""v2.25：菜单默认快捷键接线 + 插件详情入口"""


def test_default_shortcut_applied(qapp):
    from PyQt5.QtWidgets import QAction, QMainWindow, QMenu

    from ui.default_shortcuts import apply_default_shortcuts

    win = QMainWindow()
    menu = QMenu("工具", win)
    act = QAction("🧩 插件市场", win)
    menu.addAction(act)
    win.menuBar().addMenu(menu)
    try:
        assert apply_default_shortcuts(win) >= 1
        assert act.shortcut().toString() == "Ctrl+Shift+M"
    finally:
        win.close()


def test_mainwindow_applies_shortcuts_static():
    src = open("ui/main_window.py", encoding="utf-8").read()
    assert "apply_default_shortcuts(self)" in src


def test_plugin_card_has_visible_detail_button():
    src = open("ui/plugin_store.py", encoding="utf-8").read()
    assert 'setText("详情")' in src
