# -*- coding: utf-8 -*-
"""窗口级拖放打开（NPP 对齐）测试"""


def _close(win):
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()


def test_window_accepts_drops(qapp):
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        assert win.acceptDrops() is True
        assert hasattr(win, "_open_dropped_paths")
        assert hasattr(win, "dropEvent")
    finally:
        _close(win)


def test_open_dropped_file_paths(qapp, tmp_path):
    from PyQt5.QtCore import QMimeData, QPoint, Qt, QUrl
    from PyQt5.QtGui import QDropEvent

    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        f1 = tmp_path / "a.txt"
        f1.write_text("a\n", encoding="utf-8")
        f2 = tmp_path / "b.txt"
        f2.write_text("b\n", encoding="utf-8")

        n = win._open_dropped_paths([str(f1), str(f2)])
        assert n == 2
        assert win.tabs.count() == 2

        # 真实 dropEvent 路径
        f3 = tmp_path / "c.txt"
        f3.write_text("c\n", encoding="utf-8")
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(str(f3))])
        ev = QDropEvent(QPoint(5, 5), Qt.CopyAction, md,
                        Qt.LeftButton, Qt.NoModifier)
        win.dropEvent(ev)
        assert win.tabs.count() == 3
    finally:
        _close(win)
