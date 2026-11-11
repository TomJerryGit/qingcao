# -*- coding: utf-8 -*-
"""v2.25 UX：动态快捷键参考"""

from PyQt5.QtWidgets import QAction, QMainWindow, QMenu


def _window():
    win = QMainWindow()
    file_menu = QMenu("文件", win)
    a = QAction("新建文件", win)
    a.setShortcut("Ctrl+N")
    b = QAction("打开文件", win)
    file_menu.addAction(a)
    file_menu.addAction(b)
    win.menuBar().addMenu(file_menu)
    return win


def test_collect_rows(qapp):
    from ui.shortcuts_dialog import collect_shortcut_rows

    win = _window()
    try:
        rows = collect_shortcut_rows(win)
        assert ("文件", "新建文件", "Ctrl+N") in rows
        assert any(r[1] == "打开文件" and r[2] == "" for r in rows)
    finally:
        win.close()


def test_dialog_filter_and_stats(qapp):
    from ui.shortcuts_dialog import ShortcutListDialog

    win = _window()
    try:
        dlg = ShortcutListDialog(win)
        assert dlg.tree.topLevelItemCount() == 2
        dlg.search.setText("新建")
        assert dlg.tree.topLevelItemCount() == 1
        assert "2 项" in dlg.status.text() or "1 项" in dlg.status.text()
        dlg.close()
    finally:
        win.close()


def test_help_menu_has_f1_and_dynamic_wiring():
    src = open("ui/mixins/menu_builder_mixin.py", encoding="utf-8").read()
    assert '"F1"' in src and "快捷键参考" in src
    src2 = open("ui/mixins/window_actions_mixin.py", encoding="utf-8").read()
    assert "ShortcutListDialog" in src2
