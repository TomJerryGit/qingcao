# -*- coding: utf-8 -*-
"""主题菜单选中对比度"""


def test_high_contrast_menu_selected_black():
    from infrastructure.theme_loader import ThemeLoader, _readable_fg

    assert _readable_fg("#ffff00") == "#000000"
    theme = ThemeLoader().load_by_name("high_contrast")
    qss = ThemeLoader().build_qss(theme)
    assert "QMenu::item:selected" in qss
    assert "color: #000000;" in qss
