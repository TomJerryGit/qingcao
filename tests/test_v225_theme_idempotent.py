# -*- coding: utf-8 -*-
"""v2.25 性能：apply_startup_theme 幂等（重复调用跳过主题重应用）"""


def test_startup_theme_cached(qapp):
    import types

    from ui.main_window import MainWindow

    fake = types.SimpleNamespace()
    fake._startup_theme = object()
    fake._startup_theme_key = "__builtin__"
    out = MainWindow.apply_startup_theme(fake)
    assert out is fake._startup_theme
