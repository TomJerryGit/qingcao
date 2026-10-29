# -*- coding: utf-8 -*-
"""v2.15：沙箱诊断按文件聚合"""
from unittest.mock import patch

import pytest

from ui.main_window import MainWindow


class FakeDocument:
    def __init__(self, filepath):
        self.filepath = filepath


class FakeProxy:
    def __init__(self, filepath, text):
        self.document = FakeDocument(filepath)
        self._text = text

    def get_text(self):
        return self._text


class FakeEditor:
    def __init__(self, filepath, text):
        self.proxy = FakeProxy(filepath, text)


class FakeTabs:
    def __init__(self, editors, current=0):
        self._editors = editors
        self._current = current

    def count(self):
        return len(self._editors)

    def widget(self, i):
        return self._editors[i]

    def currentIndex(self):
        return self._current


class FakeSp:
    def diagnostics(self, text):
        return [{"line": 1, "col": 0, "severity": "info",
                 "message": "d:%d" % len(text)}] if text else []


class FakeManager:
    def __init__(self):
        self.files = {}

    def get_for_file(self, fp):
        return []

    def set_file_problems(self, fp, problems):
        self.files[fp] = problems


def _close(win):
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()


def test_aggregate_all_files(qapp):
    win = MainWindow()
    mgr = FakeManager()
    tabs = FakeTabs([FakeEditor("a.py", "x" * 3),
                     FakeEditor("b.py", "y" * 5)])
    try:
        with patch.object(win, "_get_sandboxed_plugins",
                          return_value={"dummy": FakeSp()}), \
             patch.object(win, "tabs", tabs), \
             patch("core.problems.get_problem_manager",
                   return_value=mgr):
            total = win.run_sandboxed_diagnostics(all_files=True)
        assert total == 2
        assert set(mgr.files) == {"a.py", "b.py"}
        assert len(mgr.files["a.py"]) == 1
        assert mgr.files["a.py"][0].message == "d:3"
        assert mgr.files["b.py"][0].message == "d:5"
    finally:
        _close(win)


def test_live_only_current_file(qapp):
    win = MainWindow()
    tabs = FakeTabs([FakeEditor("a.py", "x"), FakeEditor("b.py", "yy")])
    try:
        with patch.object(win, "_get_sandboxed_plugins",
                          return_value={"dummy": FakeSp()}), \
             patch.object(win, "tabs", tabs), patch.object(win, "run_sandboxed_diagnostics",
                          return_value=7) as m, patch.object(win, "_sandbox_live_enabled",
                          return_value=True):
            win._run_live_sandbox_diagnostics()
        m.assert_called_once_with(all_files=False)
    finally:
        _close(win)