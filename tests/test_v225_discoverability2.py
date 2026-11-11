# -*- coding: utf-8 -*-
"""v2.25 发现性：工具栏 tooltip 快捷键 + 命令面板最近使用分组"""

import time


def test_toolbar_tooltips_include_shortcuts(qapp):
    from PyQt5.QtWidgets import QAction, QToolBar

    from ui.default_shortcuts import apply_toolbar_tooltips

    tb = QToolBar()
    a = QAction("保存", tb)
    b = QAction("命令面板", tb)
    tb.addAction(a)
    tb.addAction(b)
    try:
        assert apply_toolbar_tooltips(tb) >= 1
        assert "Ctrl+S" in a.toolTip()
        assert "Ctrl+Shift+P" in b.toolTip()
    finally:
        tb.deleteLater()


def test_palette_recent_group_header(qapp):
    from ui.command_palette import BasePalette, PaletteItem, PaletteMode

    p = BasePalette(None, PaletteMode.COMMAND)
    try:
        a = PaletteItem(title="A", action_name="a")
        b = PaletteItem(title="B", action_name="b")
        p.set_items([a, b])
        p.set_usage_history({"action:b": (time.time(), 2)})
        p._refresh()
        assert p._row_items[0] is None  # 「最近使用」标题
        assert p._row_items[1] is b
        # 导航跳过标题：从标题行向下应选中 B
        p.list_widget.setCurrentRow(0)
        p._move_selection(1)
        assert p.list_widget.currentRow() == 1
        # 回车执行最近使用的 B
        got = []
        p.item_selected.connect(lambda item: got.append(item.action_name))
        p._on_return_pressed()
        assert got == ["b"]
    finally:
        p.close()
