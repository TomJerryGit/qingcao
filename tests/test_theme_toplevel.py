# -*- coding: utf-8 -*-
"""C-2：独立顶层对话框主题覆盖测试"""
from PyQt5.QtWidgets import QApplication, QDialog, QMenu


QSS = "QDialog { background-color: #ffffff; color: #000000; }"


def test_apply_theme_to_existing_toplevel(qapp):
    from ui.main_window import MainWindow
    win = MainWindow()
    dlg = QDialog()
    try:
        win._current_theme_qss = QSS
        n = win._apply_theme_to_top_levels(QSS)
        assert n >= 1
        assert dlg.styleSheet() == QSS
    finally:
        try:
            sess = getattr(win, "session", None)
            if sess is not None and hasattr(sess, "save"):
                sess.save = lambda *a, **k: None
        except Exception:
            pass
        dlg.close()
        win.close()


def test_theme_filter_styles_new_dialog(qapp):
    from ui.main_window import MainWindow
    win = MainWindow()
    dlg = QDialog()
    try:
        win._current_theme_qss = QSS
        win._ensure_toplevel_theme_filter()
        dlg.show()
        QApplication.processEvents()
        assert dlg.styleSheet() == QSS
    finally:
        try:
            sess = getattr(win, "session", None)
            if sess is not None and hasattr(sess, "save"):
                sess.save = lambda *a, **k: None
        except Exception:
            pass
        dlg.close()
        win.close()


def test_menu_not_styled(qapp):
    from ui.main_window import MainWindow
    win = MainWindow()
    menu = QMenu()
    try:
        win._current_theme_qss = QSS
        win._apply_theme_to_top_levels(QSS)
        assert menu.styleSheet() != QSS
    finally:
        try:
            sess = getattr(win, "session", None)
            if sess is not None and hasattr(sess, "save"):
                sess.save = lambda *a, **k: None
        except Exception:
            pass
        menu.close()
        win.close()