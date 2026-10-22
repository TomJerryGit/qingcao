# -*- coding: utf-8 -*-
"""欢迎页可关闭（NPP 默认无欢迎页）测试"""


def _close(win):
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()


def test_welcome_page_toggle(qapp):
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        act = win.welcome_page_action
        assert act is not None and act.isCheckable()

        win._set_welcome_page_enabled(False)
        assert win.prefs.get("show_welcome_page", None) in (False, "false")
        assert win.central_stack.currentIndex() == 0

        win._set_welcome_page_enabled(True)
        if win.tabs.count() == 0:
            assert win.central_stack.currentIndex() == 1
    finally:
        try:
            win.prefs.set("show_welcome_page", True)
        except Exception:
            pass
        _close(win)
