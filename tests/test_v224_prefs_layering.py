# -*- coding: utf-8 -*-
"""v2.24.x UX：设置基础/高级分层"""


def test_advanced_tab_layering(qapp):
    from PyQt5.QtCore import Qt

    from ui.preferences_panel import PAGES, PreferencesDialog

    dlg = PreferencesDialog(None)
    try:
        idx = next(i for i, (k, _n, _i) in enumerate(PAGES) if k == "advanced")
        item = dlg.category_list.item(idx)
        assert item is not None
        # 默认隐藏高级
        dlg._toggle_advanced(False)
        assert item.isHidden() is True
        assert dlg.advanced_check.isChecked() is False
        # 勾选后显示
        dlg._toggle_advanced(True)
        assert item.isHidden() is False
    finally:
        dlg.close()
