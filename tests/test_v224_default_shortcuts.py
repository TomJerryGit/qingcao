# -*- coding: utf-8 -*-
"""v2.24.x UX：菜单默认快捷键兜底"""


def test_apply_default_shortcuts(qapp):
    from PyQt5.QtWidgets import QAction, QMainWindow, QMenu

    from ui.default_shortcuts import apply_default_shortcuts

    win = QMainWindow()
    menu = QMenu("文件", win)
    a = QAction("新建文件", win)
    b = QAction("保存", win)
    c = QAction("已自带快捷键", win)
    c.setShortcut("Ctrl+Shift+Q")
    menu.addAction(a)
    menu.addAction(b)
    menu.addAction(c)
    win.menuBar().addMenu(menu)
    try:
        assert apply_default_shortcuts(win) == 2
        assert a.shortcut().toString() == "Ctrl+N"
        assert b.shortcut().toString() == "Ctrl+S"
        assert c.shortcut().toString() == "Ctrl+Shift+Q"
        assert apply_default_shortcuts(win) == 0
    finally:
        win.close()
