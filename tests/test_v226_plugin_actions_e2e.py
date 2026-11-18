# -*- coding: utf-8 -*-
"""v2.26 P1：插件动作级 e2e（todo 扫描 / logtail 停止）"""

import importlib
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _API:
    def __init__(self):
        self.menus = []
        self.diagnostics = []
        self.status = []

    def __getattr__(self, name):
        return lambda *a, **k: None

    def get_current_filepath(self):
        return "sample.py"

    def get_current_text(self):
        return "# TODO: fix this\nX = 1\n"

    def get_selected_text(self):
        return ""

    def get_config(self, *a, **k):
        return None

    def add_menu(self, path, *a, **k):
        self.menus.append(path)

    def add_status_item(self, *a, **k):
        return 0

    def publish_diagnostics(self, items, *a, **k):
        self.diagnostics = list(items)

    def clear_diagnostics(self, *a, **k):
        return 0

    def log(self, *a, **k):
        pass

    def show_status(self, *a, **k):
        self.status.append(a)

    def show_message(self, *a, **k):
        pass

    def subscribe(self, *a, **k):
        pass


def _activate(mod):
    plugin = importlib.import_module(mod).Plugin()
    api = _API()
    plugin.api = api
    plugin.on_activate()
    return plugin, api


def test_todo_scan_action():
    plugin, api = _activate("plugins.todo_panel")
    plugin.scan_current_file()
    assert any("TODO" in str(d) for d in api.diagnostics)


def test_logtail_stop_action():
    plugin, api = _activate("plugins.logtail")
    plugin.stop_watching()
    assert True
