# -*- coding: utf-8 -*-
"""NPP 式菜单重组测试（搜索/宏/运行/窗口，非破坏式）"""


def _close(win):
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()


def _titles(win):
    return [a.text() for a in win.menuBar().actions() if a.text()]


def test_npp_menus_added_without_breaking_shortcuts(qapp):
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        titles = " | ".join(_titles(win))
        for name in ("搜索", "宏", "运行", "窗口"):
            assert name in titles, "缺少「%s」菜单: %s" % (name, titles)
        # 旧菜单仍在
        for name in ("文件", "编辑", "视图", "工具", "帮助"):
            assert name in titles, "旧菜单被破坏: %s" % (name,)

        # 新菜单项不得绑定快捷键（避免 ambiguous shortcut）
        for attr in ("npp_search_menu", "npp_macro_menu",
                     "npp_run_menu", "npp_window_menu"):
            menu = getattr(win, attr, None)
            assert menu is not None, "缺少菜单 %s" % attr
            for act in menu.actions():
                if act.isSeparator():
                    continue
                assert act.shortcut().isEmpty(),                     "%s 的菜单项 %r 绑定了快捷键 %r" % (
                        attr, act.text(), act.shortcut().toString())

        assert len(win.npp_search_menu.actions()) >= 6
        assert len(win.npp_run_menu.actions()) >= 1
        assert len(win.npp_window_menu.actions()) >= 3
    finally:
        _close(win)
