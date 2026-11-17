# -*- coding: utf-8 -*-
"""v2.26 P2：#6 低覆盖插件补充测试"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _API:
    def __init__(self, text="abc"):
        self.text = text
        self.status = []
        self.messages = []
        self.menus = []
        self.settings = []

    def get_current_text(self):
        return self.text

    def get_config(self, key, default=None):
        return default

    def log(self, *a, **k):
        pass

    def show_status(self, *a, **k):
        self.status.append(a)

    def show_message(self, *a, **k):
        self.messages.append(a)

    def add_menu(self, path, *a, **k):
        self.menus.append(path)

    def add_status_item(self, *a, **k):
        return 0

    def register_settings_schema(self, schema, *a, **k):
        self.settings.append(schema)


def test_my_plugin_action():
    from plugins.my_plugin import Plugin

    plugin = Plugin()
    plugin.api = _API("hello")
    plugin.on_activate()
    plugin.run_action()
    assert plugin.api.messages
    assert "5" in str(plugin.api.messages[0])


def test_demo_show_stats():
    from plugins.demo import Plugin

    plugin = Plugin()
    plugin.api = _API("abcd")
    plugin.on_activate()
    plugin.show_stats()
    assert "4" in str(plugin.api.messages[0])


def test_logtail_filter_highlight_helpers():
    from plugins.logtail import filter_lines, find_matches

    text = "INFO ok\nERROR bad"
    assert filter_lines(text, "ERROR") == "ERROR bad"
    assert find_matches(text, "ERROR") == [(8, 13)]
