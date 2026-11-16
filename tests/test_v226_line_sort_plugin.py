# -*- coding: utf-8 -*-
"""v2.26 P4：line_sort 模板采用插件 + 市场快捷键"""

import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _API:
    def __init__(self, selected):
        self.selected = selected
        self.replaced = None
        self.status = []

    def get_selected_text(self):
        return self.selected

    def get_current_text(self):
        return self.selected

    def replace_selected_text(self, text):
        self.replaced = text

    def set_editor_text(self, text):
        self.replaced = text

    def get_config(self, key, default=None):
        return default

    def log(self, *a, **k):
        pass

    def show_status(self, *a, **k):
        self.status.append(a)

    def show_message(self, *a, **k):
        pass

    def add_menu(self, *a, **k):
        pass

    def add_status_item(self, *a, **k):
        return None

    def register_settings_schema(self, *a, **k):
        pass


def test_sort_selection_ascending_case_insensitive():
    from plugins.line_sort import Plugin

    api = _API("b\na\nB")
    plugin = Plugin()
    plugin.api = api
    n = plugin._sort(False)
    assert n == 3
    assert api.replaced == "a\nb\nB"


def test_sort_dedupe_descending():
    from plugins.line_sort import Plugin

    api = _API("b\na\nb")
    plugin = Plugin()
    plugin.api = api
    plugin._sort(True, True)
    assert api.replaced == "b\na"


def test_plugin_manifest():
    p = os.path.join(ROOT, "plugins", "line_sort", "plugin.json")
    data = json.load(open(p, encoding="utf-8"))
    assert data["name"] == "line_sort"
    assert "editor_read" in data["permissions"]


def test_market_has_ctrl_f_and_esc():
    src = open(os.path.join(ROOT, "ui", "plugin_store.py"), encoding="utf-8").read()
    assert "Ctrl+F" in src and "Key_Escape" in src
