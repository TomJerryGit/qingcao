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


def test_encoding_and_language_menus(qapp, tmp_path):
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        titles = " | ".join(_titles(win))
        assert "编码" in titles and "语言" in titles, titles

        enc = [a.text() for a in win.npp_encoding_menu.actions()
               if not a.isSeparator()]
        assert len(enc) >= 3, enc
        assert any("UTF-8" in t for t in enc), enc

        lang = [a.text() for a in win.npp_language_menu.actions()
                if not a.isSeparator()]
        assert any("自动" in t for t in lang), lang

        # 自动语言识别：打开文件后触发不应崩溃
        f = tmp_path / "a.py"
        f.write_text("x = 1\n", encoding="utf-8")
        win.tabs.open_file(str(f))
        win._apply_language_by_extension()
    finally:
        _close(win)


def test_settings_menu(qapp):
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        titles = " | ".join(_titles(win))
        assert "设置" in titles, titles
        items = [a.text() for a in win.npp_settings_menu.actions()
                 if not a.isSeparator()]
        assert len(items) >= 8, items
        for key in ("首选项", "快捷键", "主题", "配置", "语言包"):
            assert any(key in t for t in items), "缺少 %s 类条目: %r" % (
                key, items)
        # 新菜单项不绑快捷键
        for act in win.npp_settings_menu.actions():
            if act.isSeparator() or act.menu() is not None:
                continue
            assert act.shortcut().isEmpty(), act.text()
        assert hasattr(win, "_open_language_packs_dir")
    finally:
        _close(win)
