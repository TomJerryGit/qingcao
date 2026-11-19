# -*- coding: utf-8 -*-
"""Sprint 2：向导结果应用"""

import os


class _Page:
    def __init__(self, plugins, sample):
        self._plugins = plugins
        self._sample = sample

    def get_plugins(self):
        return self._plugins

    def get_sample(self):
        return self._sample


class _Wizard:
    def __init__(self):
        self.plugins_page = _Page(["line_sort"], "python")
        self.sample_page = _Page([], "python")


class _Tabs:
    def __init__(self):
        self.opened = []

    def open_file(self, path):
        self.opened.append(path)


class _Win:
    def __init__(self):
        self.tabs = _Tabs()


def test_apply_selections_opens_sample(qapp):
    from ui.first_run_wizard import apply_wizard_selections

    win = _Win()
    path = apply_wizard_selections(win, _Wizard())
    assert path and os.path.isfile(path)
    assert win.tabs.opened == [path]
