# -*- coding: utf-8 -*-
"""v2.12.0 P0：多实例冲突检测 + 重复事件抑制"""
import os
from unittest.mock import patch


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _FakeReload:
    def __init__(self):
        self.calls = []

    def __call__(self, path, editor):
        self.calls.append((path, editor))


def _close(win):
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()


def _open(win, tmp_path, name="conflict.txt"):
    f = tmp_path / name
    f.write_text("hello\n", encoding="utf-8")
    win.tabs.open_file(str(f))
    return str(f), win.tabs.widget(0)


def test_conflict_prompt_and_reload(qapp, tmp_path):
    from PyQt5.QtWidgets import QMessageBox

    from ui.main_window import MainWindow
    win = MainWindow()
    try:
        path, editor = _open(win, tmp_path)
        doc_cls = type(editor.document)
        reload = _FakeReload()
        win.tabs._reload_file = reload
        with patch.object(doc_cls, "is_modified",
                          property(lambda self: True)):
            with patch.object(QMessageBox, "question",
                              return_value=QMessageBox.No):
                win._on_remote_file_saved(path, 1.0, 999999)
            assert reload.calls == []
            assert win._last_remote_conflict["path"] == path
            with patch.object(QMessageBox, "question",
                              return_value=QMessageBox.Yes):
                win._on_remote_file_saved(path, 1.0, 999999)
        assert reload.calls and reload.calls[0][0] == path
        assert win._last_remote_conflict is None
    finally:
        _close(win)


def test_no_conflict_auto_reload(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow()
    try:
        path, editor = _open(win, tmp_path, "auto.txt")
        reload = _FakeReload()
        win.tabs._reload_file = reload
        doc_cls = type(editor.document)
        with patch.object(doc_cls, "is_modified",
                          property(lambda self: False)):
            win._on_remote_file_saved(path, 1.0, 999999)
        assert reload.calls and reload.calls[0][0] == path
    finally:
        _close(win)


def test_duplicate_open_event_suppressed(qapp, tmp_path):
    import infrastructure.instance_broadcast as ib
    from ui.main_window import MainWindow
    win = MainWindow()
    calls = []
    try:
        path, _editor = _open(win, tmp_path, "dup.txt")
        win._known_open_paths = {path}
        with patch.object(ib, "notify_file_event",
                          side_effect=lambda k, p: calls.append((k, p))):
            win._on_local_tab_opened(0)
        assert calls == []
        win._known_open_paths = set()
        with patch.object(ib, "notify_file_event",
                          side_effect=lambda k, p: calls.append((k, p))):
            win._on_local_tab_opened(0)
        assert calls and calls[0][0] == "file_opened"
    finally:
        _close(win)


def test_conflict_wired_static():
    src = open(os.path.join(ROOT, "ui", "main_window.py"),
               encoding="utf-8").read()
    assert "_last_remote_conflict" in src
    assert "保存冲突" in src