# -*- coding: utf-8 -*-
"""Sprint 2：首次启动向导完整流程"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _Page:
    def __init__(self, plugins, sample):
        self._plugins, self._sample = plugins, sample

    def get_plugins(self):
        return self._plugins

    def get_sample(self):
        return self._sample


class _Wizard:
    def __init__(self, plugins, sample):
        self.plugins_page = _Page(plugins, sample)
        self.sample_page = _Page([], sample)


class _Tabs:
    def __init__(self):
        self.opened = []

    def open_file(self, path):
        self.opened.append(path)


class _Win:
    def __init__(self):
        self.tabs = _Tabs()


def test_wizard_pages_and_skip(qapp):
    from ui.first_run_wizard import FirstRunWizard

    w = FirstRunWizard()
    try:
        assert len(w.pageIds()) >= 6
        assert w.plugins_page.get_plugins()
        assert w.sample_page.get_sample() == "python"
    finally:
        w.close()


def test_apply_plugins_and_skip_sample(qapp):
    from PyQt5.QtCore import QSettings

    from ui.first_run_wizard import apply_wizard_selections

    s = QSettings("QingCao", "Plugins")
    s.setValue("disabled", ["line_sort", "wordcount"])
    win = _Win()
    path = apply_wizard_selections(win, _Wizard(["line_sort"], ""))
    assert path is None and win.tabs.opened == []
    disabled = QSettings("QingCao", "Plugins").value("disabled", [], type=list)
    assert "line_sort" not in disabled
