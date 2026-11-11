# -*- coding: utf-8 -*-
"""v2.25 UX：命令面板分类筛选"""


def test_category_filter(qapp):
    from ui.command_palette import BasePalette, PaletteItem, PaletteMode

    p = BasePalette(None, PaletteMode.COMMAND)
    try:
        items = [
            PaletteItem(title="保存", category="命令", action_name="save"),
            PaletteItem(title="打开文件", category="文件"),
            PaletteItem(title="主题", category="主题"),
        ]
        p.set_items(items)
        assert p.category_combo.count() == 4  # 全部 + 3 类
        p.category_combo.setCurrentText("命令")
        assert len(p.filtered_items) == 1
        assert p.filtered_items[0].title == "保存"
        p.category_combo.setCurrentText("全部")
        assert len(p.filtered_items) == 3
    finally:
        p.close()
