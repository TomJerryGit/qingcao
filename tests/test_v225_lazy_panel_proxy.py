# -*- coding: utf-8 -*-
"""v2.25 性能：面板惰性属性代理 + 非关键面板首帧后预热"""


def test_lazy_panel_attribute_proxy(qapp):
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        # 未预先置 None 的面板（如 terminal/lsp）由代理按需构造
        assert win.terminal is not None
        assert "terminal" in win._panels_built
        assert win.lsp is not None
    finally:
        win.close()


def test_secondary_panels_prewarmed_after_events(qapp):
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        assert "plugins_panel" not in win._panels_built  # 尚未构造
        win._prewarm_secondary_panels()
        assert "plugins_panel" in win._panels_built
        assert win.perf_monitor is not None
    finally:
        win.close()
