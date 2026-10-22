# -*- coding: utf-8 -*-
"""打印/打印预览（NPP 对齐）测试"""


def _close(win):
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()


def test_print_actions_and_document_builder(qapp, tmp_path):
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        texts = [a.text() for a in win.file_menu.actions()]
        assert any("打印" in t and "预览" not in t for t in texts), texts
        assert any("打印预览" in t for t in texts), texts
        assert hasattr(win, "_print_document")
        assert hasattr(win, "_print_preview")

        f = tmp_path / "p.py"
        f.write_text("print('hello')\n", encoding="utf-8")
        win.tabs.open_file(str(f))
        doc, proxy = win._build_print_document()
        assert proxy is not None
        assert "print('hello')" in doc.toPlainText()
        assert doc.characterCount() > 5
    finally:
        _close(win)
