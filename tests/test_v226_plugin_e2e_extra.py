# -*- coding: utf-8 -*-
"""v2.26 P1：插件激活/菜单 e2e（logtail/todo/git_deep）"""

import importlib
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _API:
    def __init__(self):
        self.menus = []
        self.status = []

    def __getattr__(self, name):
        return lambda *a, **k: [] if name.startswith("all_") else None

    def get_current_filepath(self):
        return ""

    def get_current_text(self):
        return "TODO: x\n"

    def get_selected_text(self):
        return ""

    def get_config(self, *a, **k):
        return None

    def add_menu(self, path, *a, **k):
        self.menus.append(path)

    def add_status_item(self, *a, **k):
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


def test_logtail_todo_git_menus():
    for mod in ("plugins.logtail", "plugins.todo_panel", "plugins.git_deep"):
        plugin, api = _activate(mod)
        assert api.menus, mod
        try:
            plugin.on_deactivate()
        except Exception:
            pass
