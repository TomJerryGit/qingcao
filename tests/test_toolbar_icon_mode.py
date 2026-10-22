# -*- coding: utf-8 -*-
"""工具栏图标模式（NPP 风格）测试"""


def _close(win):
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()


def test_toolbar_icon_mode_toggle(qapp):
    from PyQt5.QtCore import Qt

    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        act = win.toolbar_icon_action
        assert act is not None and act.isCheckable()

        win._set_toolbar_icon_mode(True)
        assert win.toolbar.toolButtonStyle() == Qt.ToolButtonIconOnly
        with_icon = [a for a in win.toolbar.actions()
                     if not a.isSeparator() and not a.icon().isNull()]
        assert len(with_icon) >= 3, [a.text() for a in win.toolbar.actions()]

        win._set_toolbar_icon_mode(False)
        assert win.toolbar.toolButtonStyle() == Qt.ToolButtonTextOnly
        restored = [a.text() for a in win.toolbar.actions()
                    if not a.isSeparator() and a.text()]
        assert restored, "关闭图标模式后文字未恢复"
    finally:
        try:
            win.prefs.set("toolbar_icon_mode", False)
        except Exception:
            pass
        _close(win)
