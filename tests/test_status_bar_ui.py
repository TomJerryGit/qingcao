# -*- coding: utf-8 -*-
"""NPP 式状态栏交互测试（行/列可点击跳转 + tooltip）"""


def _close(win):
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()


def test_status_bar_labels_have_tooltips(qapp):
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        assert win.cursor_label.toolTip(), "行/列标签缺少 tooltip"
        for attr in ("encoding_label", "eol_label", "mode_label"):
            label = getattr(win, attr, None)
            assert label is not None
            assert label.toolTip(), "%s 缺少 tooltip" % attr
    finally:
        _close(win)


def test_cursor_label_click_jumps_to_line(qapp, tmp_path):
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        f = tmp_path / "a.py"
        f.write_text("a = 1\nb = 2\n", encoding="utf-8")
        win.tabs.open_file(str(f))
        called = {"n": 0}
        editor = win.tabs.current_proxy().sc
        editor._trigger_goto_line = lambda: called.__setitem__("n", 1)

        win.cursor_label.clicked.emit()
        assert called["n"] == 1, "点击行列标签未触发跳转到行"
    finally:
        _close(win)


def test_length_label_and_stats(qapp, tmp_path):
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        assert win.length_label.toolTip(), "长度标签缺少 tooltip"
        f = tmp_path / "s.txt"
        f.write_text("hello world\nabc\n", encoding="utf-8")
        win.tabs.open_file(str(f))
        win._update_status_for_editor()
        assert win.length_label.text().startswith("长度: ")
        s = win._status_stats()
        # Scintilla 行数 = 换行符数 + 1（末尾换行也算一行）
        assert s["lines"] == 3
        assert s["chars"] >= 15
        assert s["words"] == 3
        assert s["bytes"] >= s["chars"]
    finally:
        _close(win)
