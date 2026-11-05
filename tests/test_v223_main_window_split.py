# -*- coding: utf-8 -*-
"""v2.23 D2：ui/main_window.py 拆分结构回归"""

import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIXINS = (
    "window_theme_mixin",
    "window_lsp_mixin",
    "window_remote_mixin",
    "window_actions_mixin",
    "window_session_mixin",
)


def test_main_window_split_structure():
    lines = len(open(os.path.join(ROOT, "ui", "main_window.py"), encoding="utf-8").readlines())
    assert lines < 1200, "main_window.py 拆分后应 < 1200 行，当前 %d" % lines
    assert os.path.isfile(os.path.join(ROOT, "ui", "main_window_common.py"))
    for name in MIXINS:
        assert os.path.isfile(os.path.join(ROOT, "ui", "mixins", name + ".py"))
    from ui.main_window import MainWindow

    bases = [c.__name__ for c in MainWindow.__mro__[1:6]]
    assert bases == [
        "WindowThemeMixin",
        "WindowLSPMixin",
        "WindowRemoteMixin",
        "WindowActionsMixin",
        "WindowSessionMixin",
    ], bases
    for name in (
        "save_session",
        "restore_session",
        "closeEvent",
        "_shutdown_background_work",
        "_on_global_replace",
        "apply_theme_to_widget",
        "_start_instance_broadcast",
    ):
        assert hasattr(MainWindow, name), name
